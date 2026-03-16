# Music Organizer

`music-organizer` este un utilitar CLI în Python, conceput cu accent pe siguranță, pentru curățarea și organizarea unei biblioteci muzicale locale dezordonate pe Windows sau pe orice altă platformă compatibilă cu Python 3.12.

Aplicația scanează recursiv fișierele audio suportate, citește tagurile existente cu `mutagen`, încearcă o identificare online conservatoare prin MusicBrainz, poate folosi opțional fingerprinting audio prin AcoustID, rescrie metadatele normalizate pentru potrivirile de încredere și organizează fișierele într-o structură predictibilă, fără a șterge vreodată ceva.

## Formate suportate

- `.mp3`
- `.flac`
- `.m4a`
- `.opus`
- `.ogg`
- `.wav`

## Funcționalități

- Mod implicit sigur: `--dry-run` este activ implicit.
- Moduri explicite de execuție: `--copy` păstrează fișierele originale, iar `--move` le mută în noua structură.
- Strategie de identificare conservatoare:
  - folosește mai întâi tagurile existente
  - apoi încearcă inferența din numele fișierului
  - apoi caută în MusicBrainz
  - folosește iTunes Search API ca sursă suplimentară de catalog
  - folosește căutarea Last.fm atunci când `LASTFM_API_KEY` este configurată
  - folosește Discogs Database Search atunci când `DISCOGS_USER_TOKEN` este configurată
  - folosește AcoustID ca fallback pe bază de fingerprint audio atunci când `ACOUSTID_API_KEY` este configurată și există `fpcalc` sau Chromaprint
- Trimite automat în `Review` rezultatele online ambigue sau cu încredere insuficientă.
- Încearcă implicit selecția interactivă în terminal pentru rezultatele ambigue, astfel încât să alegi direct varianta corectă; dacă inputul nu poate fi citit, piesa rămâne în `Review`.
- Dacă nu există o potrivire online suficient de sigură, dar tagurile locale sunt utilizabile, piesa este organizată direct în `Matched`, cu această informație păstrată în raport.
- Gestionează în siguranță coliziunile de nume la destinație.
- Normalizează numele de fișiere și directoare pentru a fi compatibile cu Windows.
- Scrie rapoarte și loguri în UTF-8.
- Poate afișa deciziile pe fiecare fișier și warning-urile direct în terminal prin `--verbose`.
- Generează atât `report.csv`, cât și `report.json`.
- Poate genera opțional playlistul `unmatched.m3u`.

## Structura rezultatelor

Potriviri cu încredere ridicată:

```text
Matched/<AlbumArtist sau Artist>/<Album sau Singles>/<TrackNumber - Title>.<ext>
```

Structura din `Matched` poate fi personalizată din `.env` prin `MATCHED_PATH_TEMPLATE`.

Candidați ambigui sau cu încredere scăzută:

```text
Review/<calea relativă originală>
```

Metadate insuficiente sau nesigure:

```text
Unmatched/<calea relativă originală>
```

## Instalare

1. Creează și activează un mediu virtual Python 3.12.
2. Instalează dependențele:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. Opțional, creează un fișier `.env` pornind de la `.env.example` și adaugă cheile API necesare.

## Variabile de mediu

- `ACOUSTID_API_KEY`
  - Opțională.
  - Activează identificarea pe bază de fingerprint audio prin AcoustID și `pyacoustid`.
  - În practică, fingerprinting-ul necesită și un backend local precum Chromaprint sau `fpcalc`.
- `LASTFM_API_KEY`
  - Opțională.
  - Activează `track.search` din Last.fm ca sursă suplimentară de metadate.
- `DISCOGS_USER_TOKEN`
  - Opțională.
  - Activează căutarea prin Discogs Database Search ca sursă suplimentară de identificare.
  - Creezi tokenul din contul tău Discogs, secțiunea de developer settings / personal access token.
  - Pune tokenul în `.env` astfel:

```env
DISCOGS_USER_TOKEN=tokenul_tau_discogs
```
- `SEARCH_PROVIDER_ORDER`
  - Opțională.
  - Controlează ordinea providerilor de catalog.
  - Valori suportate: `musicbrainz`, `itunes`, `lastfm`, `discogs`
  - Exemplu: `SEARCH_PROVIDER_ORDER=musicbrainz,itunes,lastfm,discogs`
  - `AcoustID` nu este controlat de această variabilă; rămâne fallback separat, deoarece este mai lent și lucrează pe fingerprint audio.
- `MATCHED_PATH_TEMPLATE`
  - Opțională.
  - Controlează structura relativă a fișierelor din `Matched`.
  - Valoare implicită:

```env
MATCHED_PATH_TEMPLATE={artist}/{album}/{track_number} - {title}.{ext}
```

  - Placeholderi suportați:
    - `{artist}` = `AlbumArtist`, iar dacă lipsește, `Artist`
    - `{album}` = `Album`, iar dacă lipsește, `Singles`
    - `{track_number}` = numărul de track normalizat, de exemplu `03`
    - `{title}` = titlul piesei
    - `{ext}` = extensia fără punct, de exemplu `flac`
  - Template-ul trebuie să fie relativ și să includă cel puțin `{title}` și `{ext}`.
  - Exemplu alternativ:

```env
MATCHED_PATH_TEMPLATE={artist}/{track_number}.{title}.{ext}
```

## Utilizare

`dry-run` este modul implicit și este recomandat pentru prima rulare:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --dry-run
```

Comanda recomandată pentru folderele tale:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --dry-run
```

Pentru a vedea în terminal decizia pentru fiecare fișier procesat:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --dry-run --verbose
```

Pentru potrivirile ambigue, aplicația întreabă implicit direct în terminal ce variantă este corectă. Poți alege o variantă din listă sau `0` pentru `niciunul`, caz în care piesa rămâne în `Review`:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --dry-run
```

Dacă vrei să dezactivezi prompturile interactive și să trimiți direct rezultatele ambigue în `Review`:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --dry-run --no-interactive-review
```

Copiază fișierele organizate într-o bibliotecă nouă, păstrând originalele:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --copy
```

Mută fișierele în biblioteca organizată:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --move
```

Generează un playlist pentru fișierele neidentificate și reduce pragul minim de încredere:

```powershell
python -m app.main --input "D:\MusicRaw" --output "D:\MusicSorted" --copy --export-unmatched-playlist --min-confidence 0.80
```

## Flux de lucru recomandat

1. Rulează mai întâi un `dry-run` pe biblioteca brută.
2. Verifică `report.csv`, `report.json` și `logs/app.log`.
3. Analizează orice a fost trimis în `Review` sau `Unmatched`.
4. Dacă rezultatul simulării este corect, rulează din nou cu `--copy`.
5. Folosește `--move` doar după ce ești sigur că rezultatul final este cel dorit.

Dacă folosești `--no-dry-run` fără `--copy` sau `--move`, aplicația va executa implicit în modul `copy`, pentru a păstra modelul de siguranță.

## Strategia de potrivire

Aplicația este intenționat conservatoare. Nu tratează MusicBrainz ca sursă absolută, mai ales pentru muzică regională, rară sau greu de identificat corect.

Scorul de încredere este construit din:

- similaritatea dintre metadatele locale și metadatele candidatului
- calitatea și proveniența dovezilor
- scorul MusicBrainz sau puterea fingerprint-ului AcoustID
- confirmarea între mai multe surse atunci când mai mulți provideri întorc aceeași pereche piesă/artist
- concordanța numărului de track, atunci când este disponibil
- penalizări pentru rezultate prea apropiate sau ambigue

În practică:

- potrivirile exacte bazate pe taguri existente obțin scor mare
- potrivirile deduse doar din numele fișierului obțin scor mai mic
- iTunes și Last.fm pot confirma rezultatele MusicBrainz și pot reduce numărul de piese din `Review`
- Discogs poate confirma artistul și release-ul pentru single-uri, albume sau ediții care lipsesc din alte cataloage
- potrivirile puternice prin AcoustID pot fi acceptate chiar și atunci când tagurile locale sunt slabe
- dacă nu există o potrivire online sigură, dar tagurile locale sunt bune, piesa intră direct în `Matched`
- rezultatele apropiate sau ambigue sunt trimise în `Review`

## Rapoarte și loguri

Aplicația generează:

- `report.csv`
- `report.json`
- `logs/app.log`
- `unmatched.m3u` atunci când este activată opțiunea `--export-unmatched-playlist`

Fiecare intrare din raport include calea originală, tagurile detectate, providerul care a produs potrivirea, candidatul ales, scorul de încredere, destinația și acțiunea finală.

## Teste

Rulează testele unitare cu:

```powershell
python -m pytest
```

Suita de teste acoperă:

- parsarea numelui fișierului
- sanitizarea căilor pentru Windows
- comportamentul scorului de încredere
- logica sigură de copiere și mutare în caz de coliziuni
