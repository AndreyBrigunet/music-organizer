from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from app.models import AudioMetadata, CandidateMatch, MatchDecision
from app.utils import (
    artist_similarity,
    clamp,
    normalize_artist_for_compare,
    normalize_artist_text,
    normalize_for_compare,
    normalize_text,
    similarity,
)


FILENAME_SEPARATORS = re.compile(r"\s[-–—_]\s")
TRACK_PREFIX_RE = re.compile(r"^\s*(?P<track>\d{1,3})[\s._-]+(?P<rest>.+)$")
TRAILING_NOISE_RE = re.compile(
    r"\s*(\[(official|hq|lyrics?|live|remaster(?:ed)?|audio|video).*\]|\((official|hq|lyrics?|live|remaster(?:ed)?|audio|video).*\))\s*$",
    re.IGNORECASE,
)
ARTIST_SEPARATOR_HINT_RE = re.compile(r"(;|,|&|\bfeat(?:uring)?\.?\b|\bft\.?\b|\bx\b)", re.IGNORECASE)


def parse_filename_metadata(path: Path) -> AudioMetadata:
    candidates = parse_filename_metadata_candidates(path)
    if candidates:
        return candidates[0]
    return AudioMetadata(source="filename")


def parse_filename_metadata_candidates(path: Path) -> List[AudioMetadata]:
    stem = normalize_text(path.stem) or ""
    stem = TRAILING_NOISE_RE.sub("", stem).strip()
    stem = stem.replace("_", " ")

    track_number = None
    track_match = TRACK_PREFIX_RE.match(stem)
    if track_match:
        track_number = track_match.group("track")
        stem = normalize_text(track_match.group("rest")) or stem

    parts = [normalize_text(part) for part in FILENAME_SEPARATORS.split(stem) if normalize_text(part)]
    candidates: List[AudioMetadata] = []

    if len(parts) >= 3:
        candidates.append(
            AudioMetadata(
                artist=normalize_artist_text(parts[0]),
                album=parts[1],
                title=" - ".join(parts[2:]),
                track_number=track_number,
                source="filename",
            )
        )
        candidates.append(
            AudioMetadata(
                artist=normalize_artist_text(parts[0]),
                title=" - ".join(parts[1:]),
                track_number=track_number,
                source="filename",
            )
        )
    elif len(parts) == 2:
        first, second = parts
        forward = AudioMetadata(
            artist=normalize_artist_text(first),
            title=second,
            track_number=track_number,
            source="filename",
        )
        reverse = AudioMetadata(
            artist=normalize_artist_text(second),
            title=first,
            track_number=track_number,
            source="filename",
        )
        if _looks_like_artist(first) and not _looks_like_artist(second):
            candidates.extend([forward, reverse])
        elif _looks_like_artist(second) and not _looks_like_artist(first):
            candidates.extend([reverse, forward])
        else:
            candidates.extend([forward, reverse])
    elif len(parts) == 1:
        candidates.append(
            AudioMetadata(
                title=parts[0],
                track_number=track_number,
                source="filename",
            )
        )
    else:
        candidates.append(AudioMetadata(track_number=track_number, source="filename"))

    return _dedupe_metadata_candidates(candidates)


def score_candidate_confidence(
    candidate: CandidateMatch,
    detected_metadata: AudioMetadata,
    raw_metadata: AudioMetadata,
) -> float:
    title_similarity = similarity(detected_metadata.title, candidate.metadata.title)
    artist_similarity_score = artist_similarity(
        detected_metadata.primary_artist(),
        candidate.metadata.primary_artist(),
    )

    album_similarity = 0.0
    album_weight = 0.08
    if detected_metadata.album:
        album_similarity = similarity(detected_metadata.album, candidate.metadata.album)
    else:
        album_similarity = 1.0 if _is_likely_single(detected_metadata) else 0.5
        album_weight = 0.0 if _is_likely_single(detected_metadata) else 0.03

    track_bonus = 0.0
    if raw_metadata.track_number and candidate.metadata.track_number:
        if normalize_for_compare(raw_metadata.track_number) == normalize_for_compare(candidate.metadata.track_number):
            track_bonus = 0.05

    exact_title_match = _is_exact_match(detected_metadata.title, candidate.metadata.title)
    exact_artist_match = _is_exact_artist_match(
        detected_metadata.primary_artist(),
        candidate.metadata.primary_artist(),
    )
    has_trusted_tags = raw_metadata.has_core_identity()
    exact_bonus = 0.0
    if exact_title_match and exact_artist_match:
        exact_bonus = 0.14 if has_trusted_tags else 0.05
    elif exact_title_match:
        exact_bonus = 0.05 if has_trusted_tags else 0.02
    elif exact_artist_match:
        exact_bonus = 0.04 if has_trusted_tags else 0.01

    evidence_bonus = 0.0
    if has_trusted_tags:
        evidence_bonus += 0.10
    elif detected_metadata.source == "filename":
        evidence_bonus -= 0.08

    if _is_likely_single(detected_metadata):
        evidence_bonus += 0.02

    online_weight_by_source = {
        "musicbrainz": 0.44,
        "acoustid": 0.50,
        "itunes": 0.34,
        "deezer": 0.33,
        "lastfm": 0.28,
        "discogs": 0.22,
    }
    online_weight = online_weight_by_source.get(candidate.source, 0.30)
    confidence = (
        (title_similarity * 0.28)
        + (artist_similarity_score * 0.22)
        + (album_similarity * album_weight)
        + (candidate.raw_score * online_weight)
        + track_bonus
        + evidence_bonus
        + exact_bonus
    )

    penalties: List[str] = []
    bonuses: List[str] = []
    if track_bonus:
        bonuses.append("track-number match")
    if exact_title_match and exact_artist_match:
        bonuses.append("exact title+artist match")
    elif exact_title_match:
        bonuses.append("exact title match")
    elif exact_artist_match:
        bonuses.append("exact artist match")
    if has_trusted_tags:
        bonuses.append("trusted local tags")
    if _is_likely_single(detected_metadata):
        bonuses.append("likely single")

    if candidate.source == "musicbrainz" and candidate.raw_score < 0.85:
        confidence -= 0.08
        penalties.append("low MusicBrainz score")
    if candidate.source == "acoustid" and candidate.raw_score >= 0.90:
        confidence += 0.05
        bonuses.append("strong AcoustID fingerprint")
    if candidate.source == "lastfm":
        confidence -= 0.03
        penalties.append("Last.fm broad search penalty")
    if candidate.source == "discogs":
        confidence -= 0.06
        penalties.append("Discogs release-search penalty")
    if title_similarity < 0.80 or artist_similarity_score < 0.75:
        confidence -= 0.15
        penalties.append("weak title/artist similarity")

    candidate.title_similarity = title_similarity
    candidate.artist_similarity = artist_similarity_score
    candidate.album_similarity = album_similarity
    candidate.score_explanation = _build_score_explanation(
        title_similarity=title_similarity,
        artist_similarity_score=artist_similarity_score,
        album_similarity=album_similarity,
        raw_score=candidate.raw_score,
        source=candidate.source,
        bonuses=bonuses,
        penalties=penalties,
    )
    return clamp(confidence, 0.0, 0.99)


def is_ambiguous(best: CandidateMatch, runner_up: Optional[CandidateMatch]) -> bool:
    if runner_up is None:
        return False
    confidence_gap = best.confidence - runner_up.confidence
    if confidence_gap >= 0.08:
        return False

    different_identity = (
        normalize_for_compare(best.metadata.title) != normalize_for_compare(runner_up.metadata.title)
        or normalize_artist_for_compare(best.metadata.primary_artist()) != normalize_artist_for_compare(runner_up.metadata.primary_artist())
    )
    return different_identity and best.confidence < 0.95


class TrackMatcher:
    def __init__(
        self,
        min_confidence: float,
        search_clients: Sequence[object],
        acoustid_client: object,
        search_limit: int = 5,
    ) -> None:
        self.min_confidence = min_confidence
        self.search_clients = list(search_clients)
        self.acoustid_client = acoustid_client
        self.search_limit = search_limit

    def match(self, path: Path, raw_metadata: AudioMetadata) -> MatchDecision:
        detected_candidates = self._build_detected_metadata_candidates(path, raw_metadata)
        primary_detected_metadata = detected_candidates[0] if detected_candidates else AudioMetadata(source="filename")
        candidates, provider_trace = self._collect_candidates(path, detected_candidates, raw_metadata)
        best, runner_up = self._pick_candidates(candidates)

        if best:
            detected_metadata = best.query_metadata or primary_detected_metadata
            if is_ambiguous(best, runner_up):
                return MatchDecision(
                    action="Review",
                    detected_metadata=detected_metadata,
                    metadata_to_write=None,
                    confidence=best.confidence,
                    chosen_match=best,
                    reason="Multiple similar candidates were found; manual review required.",
                    notes=["ambiguous_online_match"],
                    review_candidates=list(candidates[:5]),
                    provider_trace=provider_trace,
                )
            if best.confidence >= self.min_confidence:
                normalized = best.metadata.merged_for_online_match(raw_metadata, source=best.source)
                return MatchDecision(
                    action="Matched",
                    detected_metadata=detected_metadata,
                    metadata_to_write=normalized,
                    confidence=best.confidence,
                    chosen_match=best,
                    reason="High-confidence online match.",
                    provider_trace=provider_trace,
                )
            if best.confidence >= max(0.55, self.min_confidence - 0.20):
                return MatchDecision(
                    action="Review",
                    detected_metadata=detected_metadata,
                    metadata_to_write=None,
                    confidence=best.confidence,
                    chosen_match=best,
                    reason="Candidate exists but confidence is below the acceptance threshold.",
                    notes=["low_confidence_candidate"],
                    review_candidates=list(candidates[:5]),
                    provider_trace=provider_trace,
                )

        if raw_metadata.has_any_identity():
            fallback_metadata = self._build_fallback_metadata(raw_metadata, path)
            return MatchDecision(
                action="Matched",
                detected_metadata=primary_detected_metadata,
                metadata_to_write=fallback_metadata,
                confidence=0.45,
                chosen_match=None,
                reason="No trusted online match found; organized using existing tags.",
                notes=["matched_by_tags"],
                provider_trace=provider_trace,
            )

        return MatchDecision(
            action="Unmatched",
            detected_metadata=primary_detected_metadata,
            metadata_to_write=None,
            confidence=0.0,
            chosen_match=None,
            reason="Not enough trustworthy metadata to classify automatically.",
            provider_trace=provider_trace,
        )

    def _build_detected_metadata_candidates(self, path: Path, raw_metadata: AudioMetadata) -> List[AudioMetadata]:
        filename_candidates = parse_filename_metadata_candidates(path)
        combined_candidates: List[AudioMetadata] = []

        if raw_metadata.has_any_identity():
            combined_candidates.append(raw_metadata)

        for filename_candidate in filename_candidates:
            combined_candidates.append(
                raw_metadata.merged_with(
                    filename_candidate,
                    source=self._merge_source(raw_metadata, filename_candidate),
                )
                if raw_metadata.has_any_identity()
                else filename_candidate
            )
            if filename_candidate.has_core_identity():
                combined_candidates.append(filename_candidate)

        if not combined_candidates:
            combined_candidates.append(AudioMetadata(source="filename"))

        return _dedupe_metadata_candidates(combined_candidates)

    def _collect_candidates(
        self,
        path: Path,
        detected_metadata_candidates: Sequence[AudioMetadata],
        raw_metadata: AudioMetadata,
    ) -> Tuple[List[CandidateMatch], List[str]]:
        candidate_map: dict[tuple[str, str], CandidateMatch] = {}
        provider_trace: List[str] = []

        for client in self.search_clients:
            provider_name = normalize_for_compare(getattr(client, "source", None))
            if not provider_name:
                provider_name = getattr(client, "__class__", type(client)).__name__.replace("Client", "").casefold() or "provider"
            if hasattr(client, "enabled") and not getattr(client, "enabled"):
                status_reason = getattr(client, "status_reason", None) or "disabled"
                provider_trace.append("{0}: skipped ({1})".format(provider_name, status_reason))
                continue

            provider_trace.append("{0}: trying".format(provider_name))
            provider_candidate_map: dict[tuple[str, str], CandidateMatch] = {}
            for detected_metadata in detected_metadata_candidates:
                if not (detected_metadata.title and detected_metadata.primary_artist()):
                    continue
                for candidate in client.search_recordings(
                    detected_metadata,
                    limit=self.search_limit,
                ):
                    candidate.query_metadata = detected_metadata
                    candidate.confidence = score_candidate_confidence(candidate, detected_metadata, raw_metadata)
                    self._store_candidate(provider_candidate_map, candidate)

            provider_candidates = list(provider_candidate_map.values())
            self._sort_candidates(provider_candidates)
            if not provider_candidates:
                provider_trace.append("{0}: no candidates".format(provider_name))
                continue
            best, runner_up = self._pick_candidates(provider_candidates)
            if best and best.confidence >= self.min_confidence and not is_ambiguous(best, runner_up):
                provider_trace.append(
                    "{0}: accepted {1:.2f}; later providers skipped".format(provider_name, best.confidence)
                )
                return provider_candidates, provider_trace

            if best:
                status = "ambiguous" if is_ambiguous(best, runner_up) else "below threshold"
                provider_trace.append(
                    "{0}: best {1:.2f} ({2}); trying next provider".format(provider_name, best.confidence, status)
                )

            for candidate in provider_candidates:
                self._store_candidate(candidate_map, candidate)

        candidates = list(candidate_map.values())
        self._apply_cross_source_corroboration(candidates)

        if not self._has_strong_candidate(candidates):
            provider_trace.append("acoustid: fallback")
            for candidate in self.acoustid_client.match_file(path):
                detected_metadata = detected_metadata_candidates[0] if detected_metadata_candidates else AudioMetadata(source="tags")
                candidate.query_metadata = detected_metadata
                candidate.confidence = score_candidate_confidence(candidate, detected_metadata, raw_metadata)
                self._store_candidate(candidate_map, candidate)
            candidates = list(candidate_map.values())
            best_acoustid, runner_up_acoustid = self._pick_candidates(candidates)
            if best_acoustid and best_acoustid.source == "acoustid":
                if best_acoustid.confidence >= self.min_confidence and not is_ambiguous(best_acoustid, runner_up_acoustid):
                    provider_trace.append("acoustid: accepted {0:.2f}".format(best_acoustid.confidence))
                else:
                    provider_trace.append("acoustid: best {0:.2f}".format(best_acoustid.confidence))
            else:
                provider_trace.append("acoustid: no usable match")

        self._sort_candidates(candidates)
        return candidates, provider_trace

    @staticmethod
    def _sort_candidates(candidates: List[CandidateMatch]) -> None:
        candidates.sort(
            key=lambda item: (
                _is_exact_match(item.query_metadata.title if item.query_metadata else None, item.metadata.title),
                _is_exact_artist_match(
                    item.query_metadata.primary_artist() if item.query_metadata else None,
                    item.metadata.primary_artist(),
                ),
                item.confidence,
            ),
            reverse=True,
        )

    @staticmethod
    def _pick_candidates(candidates: Sequence[CandidateMatch]) -> Tuple[Optional[CandidateMatch], Optional[CandidateMatch]]:
        if not candidates:
            return None, None
        best = candidates[0]
        runner_up = candidates[1] if len(candidates) > 1 else None
        return best, runner_up

    def _has_strong_candidate(self, candidates: Sequence[CandidateMatch]) -> bool:
        return any(candidate.confidence >= self.min_confidence for candidate in candidates)

    @staticmethod
    def _apply_cross_source_corroboration(candidates: Sequence[CandidateMatch]) -> None:
        grouped: dict[tuple[str, str], set[str]] = {}
        for candidate in candidates:
            key = (
                normalize_for_compare(candidate.metadata.title),
                normalize_artist_for_compare(candidate.metadata.primary_artist()),
            )
            if not all(key):
                continue
            grouped.setdefault(key, set()).add(candidate.source)

        for candidate in candidates:
            key = (
                normalize_for_compare(candidate.metadata.title),
                normalize_artist_for_compare(candidate.metadata.primary_artist()),
            )
            sources = grouped.get(key, set())
            if len(sources) <= 1:
                continue
            bonus = min(0.10, (len(sources) - 1) * 0.05)
            candidate.confidence = clamp(candidate.confidence + bonus, 0.0, 0.99)
            candidate.reason = "{0}; corroborated by {1}".format(
                candidate.reason or candidate.source,
                ", ".join(sorted(source for source in sources if source != candidate.source)),
            )
            if candidate.score_explanation:
                candidate.score_explanation = "{0}; cross-source bonus={1:.2f} ({2})".format(
                    candidate.score_explanation,
                    bonus,
                    ", ".join(sorted(source for source in sources if source != candidate.source)),
                )

    @staticmethod
    def _build_fallback_metadata(raw_metadata: AudioMetadata, path: Path) -> AudioMetadata:
        title = raw_metadata.title or normalize_text(path.stem) or "Unknown Title"
        artist = raw_metadata.artist or raw_metadata.album_artist or "Unknown Artist"
        album = raw_metadata.album or "Singles"
        return AudioMetadata(
            title=title,
            artist=artist,
            album=album,
            album_artist=raw_metadata.album_artist or raw_metadata.artist or artist,
            track_number=raw_metadata.track_number,
            disc_number=raw_metadata.disc_number,
            date=raw_metadata.date,
            genre=raw_metadata.genre,
            source="fallback-by-tags",
        )

    @staticmethod
    def _merge_source(raw_metadata: AudioMetadata, filename_metadata: AudioMetadata) -> str:
        if raw_metadata.has_any_identity() and filename_metadata.has_any_identity():
            return "tags+filename"
        if raw_metadata.has_any_identity():
            return raw_metadata.source
        return filename_metadata.source

    @staticmethod
    def _store_candidate(candidate_map: dict[tuple[str, str], CandidateMatch], candidate: CandidateMatch) -> None:
        key = _candidate_key(candidate)
        current = candidate_map.get(key)
        if current is None or candidate.confidence > current.confidence:
            candidate_map[key] = candidate


def _candidate_key(candidate: CandidateMatch) -> tuple[str, str]:
    if candidate.recording_id:
        return candidate.source, candidate.recording_id
    metadata_key = "|".join(
        [
            normalize_for_compare(candidate.metadata.title),
            normalize_artist_for_compare(candidate.metadata.primary_artist()),
            normalize_for_compare(candidate.metadata.album),
        ]
    )
    return candidate.source, metadata_key


def _dedupe_metadata_candidates(candidates: Iterable[AudioMetadata]) -> List[AudioMetadata]:
    deduped: dict[tuple[str, str, str], AudioMetadata] = {}
    for candidate in candidates:
        key = (
            normalize_for_compare(candidate.title),
            normalize_artist_for_compare(candidate.primary_artist()),
            normalize_for_compare(candidate.album),
        )
        if key in deduped:
            continue
        deduped[key] = candidate
    return list(deduped.values())


def _looks_like_artist(value: Optional[str]) -> bool:
    cleaned = normalize_text(value) or ""
    if not cleaned:
        return False
    if ARTIST_SEPARATOR_HINT_RE.search(cleaned):
        return True
    words = cleaned.split()
    if len(words) >= 2 and len(cleaned) <= 60:
        return True
    return False


def _is_exact_match(left: Optional[str], right: Optional[str]) -> bool:
    normalized_left = normalize_for_compare(left)
    normalized_right = normalize_for_compare(right)
    return bool(normalized_left and normalized_left == normalized_right)


def _is_exact_artist_match(left: Optional[str], right: Optional[str]) -> bool:
    normalized_left = normalize_artist_for_compare(left)
    normalized_right = normalize_artist_for_compare(right)
    return bool(normalized_left and normalized_left == normalized_right)


def _is_likely_single(metadata: AudioMetadata) -> bool:
    return bool(metadata.title and metadata.primary_artist() and not metadata.album)


def _build_score_explanation(
    title_similarity: float,
    artist_similarity_score: float,
    album_similarity: float,
    raw_score: float,
    source: str,
    bonuses: Sequence[str],
    penalties: Sequence[str],
) -> str:
    segments = [
        "title={0:.2f}".format(title_similarity),
        "artist={0:.2f}".format(artist_similarity_score),
        "album={0:.2f}".format(album_similarity),
        "provider={0}:{1:.2f}".format(source, raw_score),
    ]
    if bonuses:
        segments.append("bonuses={0}".format(", ".join(bonuses)))
    if penalties:
        segments.append("penalties={0}".format(", ".join(penalties)))
    return "; ".join(segments)
