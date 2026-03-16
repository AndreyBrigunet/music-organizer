from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from typing import Callable, List, Optional

import typer
from rich.console import Console
from rich.markup import escape
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn, TimeElapsedColumn
from rich.table import Table

from app.acoustid_client import AcoustIdClient
from app.config import APP_VERSION, SUPPORTED_EXTENSIONS, build_config
from app.discogs_client import DiscogsClient
from app.itunes_client import ItunesClient
from app.lastfm_client import LastFmClient
from app.matcher import TrackMatcher
from app.models import AudioMetadata, CandidateMatch, MatchDecision, ProcessingResult
from app.mover import LibraryMover
from app.musicbrainz_client import MusicBrainzClient
from app.reporter import ReportWriter
from app.scanner import LibraryScanner
from app.tags import read_metadata, write_metadata
from app.utils import safe_relative_path, setup_logging


app = typer.Typer(add_completion=False, help="Organize a local music library safely.")
console = Console()


@app.command()
def main(
    input: Path = typer.Option(..., "--input", exists=True, file_okay=False, dir_okay=True, resolve_path=True),
    output: Path = typer.Option(..., "--output", file_okay=False, dir_okay=True, resolve_path=True),
    dry_run: bool = typer.Option(
        True,
        "--dry-run/--no-dry-run",
        help="Simulate changes only. If --no-dry-run is used without --move, files are copied.",
    ),
    copy_mode: bool = typer.Option(False, "--copy", help="Copy organized files into the output library."),
    move_mode: bool = typer.Option(False, "--move", help="Move files into the output library."),
    min_confidence: float = typer.Option(0.85, "--min-confidence", min=0.0, max=1.0),
    export_unmatched_playlist: bool = typer.Option(
        False,
        "--export-unmatched-playlist",
        help="Generate unmatched.m3u with unmatched files.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        help="Show detailed per-file decisions and warnings in the terminal.",
    ),
    no_interactive_review: bool = typer.Option(
        False,
        "--no-interactive-review",
        help="Disable terminal prompts for ambiguous matches and send them directly to Review.",
    ),
) -> None:
    try:
        config = build_config(
            input_dir=input,
            output_dir=output,
            dry_run=dry_run,
            copy_mode=copy_mode,
            move_mode=move_mode,
            min_confidence=min_confidence,
            export_unmatched_playlist=export_unmatched_playlist,
        )
    except ValueError as exc:
        raise typer.BadParameter(str(exc))

    logger = setup_logging(config.logs_path, verbose=verbose, console=console)
    logger.info("Starting music organizer in %s mode", config.mode.value)
    logger.info("Input: %s", config.input_dir)
    logger.info("Output: %s", config.output_dir)

    scanner = LibraryScanner(SUPPORTED_EXTENSIONS)
    musicbrainz_client = MusicBrainzClient(logger=logger)
    itunes_client = ItunesClient(logger=logger)
    lastfm_client = LastFmClient(api_key=config.lastfm_api_key, logger=logger)
    discogs_client = DiscogsClient(user_token=config.discogs_user_token, logger=logger)
    acoustid_client = AcoustIdClient(
        api_key=config.acoustid_api_key,
        musicbrainz_client=musicbrainz_client,
        logger=logger,
    )
    search_clients_by_name = {
        "musicbrainz": musicbrainz_client,
        "itunes": itunes_client,
        "lastfm": lastfm_client,
        "discogs": discogs_client,
    }
    ordered_search_clients = [search_clients_by_name[name] for name in config.provider_order]
    matcher = TrackMatcher(
        min_confidence=config.min_confidence,
        search_clients=ordered_search_clients,
        acoustid_client=acoustid_client,
        search_limit=config.musicbrainz_limit,
    )
    mover = LibraryMover(config)
    reporter = ReportWriter(config)

    audio_files = list(scanner.scan(config.input_dir))
    console.print(
        "[bold]Music Organizer[/bold] v{0}\nMode: {1}\nFiles discovered: {2}\nProvider order: {3}\nProviders: MusicBrainz={4}, iTunes={5}, Last.fm={6}, Discogs={7}, AcoustID={8} (fallback)".format(
            APP_VERSION,
            config.mode.value,
            len(audio_files),
            " -> ".join(config.provider_order),
            musicbrainz_client.status_label,
            itunes_client.status_label,
            lastfm_client.status_label,
            discogs_client.status_label,
            acoustid_client.status_label,
        )
    )

    interactive_review_enabled = not no_interactive_review
    if interactive_review_enabled and not supports_interactive_review():
        console.print(
            "[yellow]Interactive review may be unavailable in this terminal. If input cannot be read, ambiguous matches will stay in Review.[/yellow]"
        )

    results: List[ProcessingResult] = []
    with build_progress() as progress:
        task_id = progress.add_task("Processing audio files", total=len(audio_files))
        for audio_path in audio_files:
            result = process_file(
                audio_path,
                matcher,
                mover,
                logger,
                interactive_review=interactive_review_enabled,
                pause_progress=progress.stop if interactive_review_enabled else None,
                resume_progress=progress.start if interactive_review_enabled else None,
            )
            results.append(result)
            progress.update(task_id, advance=1)
            if verbose:
                render_result(result, config.input_dir, config.output_dir)

    reporter.write_reports(results)
    logger.info("Reports written to %s and %s", config.report_csv_path, config.report_json_path)
    if config.export_unmatched_playlist:
        logger.info("Unmatched playlist written to %s", config.unmatched_playlist_path)

    render_summary(results, config.mode.value)


def process_file(
    audio_path: Path,
    matcher: TrackMatcher,
    mover: LibraryMover,
    logger,
    interactive_review: bool,
    pause_progress: Optional[Callable[[], None]] = None,
    resume_progress: Optional[Callable[[], None]] = None,
) -> ProcessingResult:
    raw_metadata = AudioMetadata(source="tags")
    try:
        raw_metadata = read_metadata(audio_path, logger=logger)
    except Exception as exc:
        logger.warning("Metadata read failed for %s: %s", audio_path, exc)

    decision = matcher.match(audio_path, raw_metadata)
    decision = maybe_resolve_review_decision(
        audio_path=audio_path,
        raw_metadata=raw_metadata,
        decision=decision,
        logger=logger,
        interactive_review=interactive_review,
        pause_progress=pause_progress,
        resume_progress=resume_progress,
    )
    destination = mover.plan_destination(audio_path, decision)
    result = ProcessingResult(
        source_path=str(audio_path),
        destination_path=str(destination),
        decision=decision,
    )

    try:
        final_destination = mover.transfer(audio_path, destination)
        result.destination_path = str(final_destination)
        result.transfer_success = True
    except Exception as exc:
        logger.exception("File transfer failed for %s", audio_path)
        result.transfer_success = False
        result.error = "transfer_failed: {0}".format(exc)
        return result

    if mover.is_dry_run():
        result.transfer_success = None
        result.tag_write_success = None
        return result

    target_for_tags = Path(result.destination_path)
    if decision.metadata_to_write and decision.action == "Matched":
        try:
            write_metadata(target_for_tags, decision.metadata_to_write, logger=logger)
            result.tag_write_success = True
        except Exception as exc:
            logger.exception("Tag write failed for %s", target_for_tags)
            result.tag_write_success = False
            result.error = "tag_write_failed: {0}".format(exc)
    else:
        result.tag_write_success = None

    return result


def render_summary(results: List[ProcessingResult], mode: str) -> None:
    counter = Counter(result.decision.action for result in results)
    table = Table(title="Run Summary")
    table.add_column("Action")
    table.add_column("Count", justify="right")
    for action in ("Matched", "Review", "Unmatched"):
        table.add_row(action, str(counter.get(action, 0)))
    table.add_row("Errors", str(sum(1 for result in results if result.error)))
    table.caption = "Mode: {0}".format(mode)
    console.print(table)


def render_result(result: ProcessingResult, input_dir: Path, output_dir: Path) -> None:
    action_styles = {
        "Matched": "green",
        "Review": "yellow",
        "Unmatched": "red",
    }
    action_style = action_styles.get(result.decision.action, "white")
    source_label = escape(str(safe_relative_path(Path(result.source_path), input_dir)))

    destination_label = "-"
    if result.destination_path:
        destination_label = escape(
            str(safe_relative_path(Path(result.destination_path), output_dir))
        )

    provider = result.decision.report_provider() or "-"
    confidence = result.decision.confidence
    metadata = result.decision.metadata_to_write or result.decision.detected_metadata
    match_label = " / ".join(
        part for part in (metadata.primary_artist(), metadata.title) if part
    ) or Path(result.source_path).name
    console.print(
        "[{style}]{action:<9}[/{style}] {confidence:.2f} via {provider} | {match} | {source} -> {destination}".format(
            style=action_style,
            action=result.decision.action.upper(),
            confidence=confidence,
            provider=escape(provider),
            match=escape(match_label),
            source=source_label,
            destination=destination_label,
        )
    )

    if result.error:
        console.print("  [red]error:[/red] {0}".format(escape(result.error)))
    elif result.decision.action != "Matched" or "matched_by_tags" in result.decision.notes:
        console.print("  [dim]{0}[/dim]".format(escape(result.decision.reason)))


def maybe_resolve_review_decision(
    audio_path: Path,
    raw_metadata: AudioMetadata,
    decision: MatchDecision,
    logger,
    interactive_review: bool,
    pause_progress: Optional[Callable[[], None]] = None,
    resume_progress: Optional[Callable[[], None]] = None,
) -> MatchDecision:
    if not interactive_review or decision.action != "Review":
        return decision

    candidates = decision.review_candidates or ([decision.chosen_match] if decision.chosen_match else [])
    if not candidates:
        return decision

    if pause_progress:
        pause_progress()
    try:
        selected_candidate = prompt_for_review_candidate(audio_path, decision.detected_metadata, candidates)
    finally:
        if resume_progress:
            resume_progress()
    if selected_candidate is None:
        logger.info("Interactive review skipped for %s; keeping Review action.", audio_path)
        return decision

    metadata_to_write = selected_candidate.metadata.merged_with(raw_metadata, source=selected_candidate.source)
    notes = list(dict.fromkeys([*decision.notes, "user_selected_candidate"]))
    logger.info(
        "Interactive review selected candidate %s for %s",
        selected_candidate.recording_id or selected_candidate.metadata.title,
        audio_path,
    )
    return MatchDecision(
        action="Matched",
        detected_metadata=selected_candidate.query_metadata or decision.detected_metadata,
        metadata_to_write=metadata_to_write,
        confidence=selected_candidate.confidence,
        chosen_match=selected_candidate,
        reason="Selected interactively by user.",
        notes=notes,
        review_candidates=candidates,
    )


def supports_interactive_review() -> bool:
    return bool(sys.stdin and sys.stdout and sys.stdin.isatty() and sys.stdout.isatty())


def prompt_for_review_candidate(
    audio_path: Path,
    detected_metadata: AudioMetadata,
    candidates: List[CandidateMatch],
) -> Optional[CandidateMatch]:
    console.print()
    console.print("[bold yellow]Manual Review Required[/bold yellow]")
    console.print("Original file: {0}".format(escape(audio_path.name)))
    console.print(
        "Detected: {0}".format(
            escape(
                " / ".join(
                    part
                    for part in (
                        detected_metadata.primary_artist(),
                        detected_metadata.title,
                        detected_metadata.album,
                    )
                    if part
                )
                or audio_path.stem
            )
        )
    )

    table = Table(title="Choose The Correct Match")
    table.add_column("No.", justify="right")
    table.add_column("Provider")
    table.add_column("Confidence", justify="right")
    table.add_column("Artist")
    table.add_column("Title")
    table.add_column("Album")
    for index, candidate in enumerate(candidates, start=1):
        table.add_row(
            str(index),
            candidate.source,
            "{0:.2f}".format(candidate.confidence),
            candidate.metadata.primary_artist() or "-",
            candidate.metadata.title or "-",
            candidate.metadata.album or "Singles",
        )
    console.print(table)
    console.print("[bold cyan]Type the number of the correct variant and press Enter. Use s or empty input to keep it in Review.[/bold cyan]")

    prompt_label = "Select a variant [1-{0}] or s to keep it in Review: ".format(len(candidates))
    while True:
        try:
            choice = input(prompt_label).strip().lower()
        except EOFError:
            console.print("[yellow]Interactive input was not available. This file will stay in Review.[/yellow]")
            return None
        except KeyboardInterrupt:
            console.print("\n[yellow]Interactive selection cancelled. This file will stay in Review.[/yellow]")
            return None
        if not choice or choice == "s":
            return None
        if choice.isdigit():
            candidate_index = int(choice)
            if 1 <= candidate_index <= len(candidates):
                return candidates[candidate_index - 1]
        console.print("[red]Invalid selection. Choose a listed number or s.[/red]")


def build_progress() -> Progress:
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        console=console,
    )


if __name__ == "__main__":
    app()
