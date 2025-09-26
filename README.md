# AI-Powered-Ftawa-Search-Engine
AI-Powered Web Application for knowledge fetching from Su'al Ahl al-Dhikr 

## Project structure
- `download/` – ingestion jobs for sourcing raw ftawa content.
- `transcribe/` – pipelines for speech-to-text and manual transcription assets.
- `preprosses/` – preprocessing utilities (tokenization, cleaning, enrichment).
- `search engine/` – core indexing and retrieval services.
- `web interface/` – end-user interface and presentation layer.
- `dependencies/` – helper scripts for managing required Python packages.

## Setup
- Create and activate the virtual environment:
	- `py -3.10 -m venv .venv`
	- `\.venv\Scripts\Activate.ps1`
- Install dependencies:
	- `pip install -r requirements.txt`
- Or run the menu option **Install project dependencies** from `python main.py`.
- Ensure FFmpeg is installed at `C:\ffmpeg` (with `ffmpeg.exe` inside `bin/`). Set the `FFMPEG_PATH` environment variable if using a different location.

## Downloading YouTube audio
1. Add each playlist URL on its own line in `download/playlists` (names will be cached automatically after the first lookup). Lines beginning with `#` are ignored.
2. Run the project driver and choose the download option:
	 - `python main.py`
3. If prompted, install project dependencies first (option 2 in the menu). Choosing not to install will exit the program.
4. Select the playlists you want to download when prompted (choose by number, name, or pick all). Subsequent runs reuse stored titles to avoid extra API calls.
5. The downloader will:
	 - Create a folder per playlist (named after the playlist title) inside `download/`.
	 - Store raw downloads temporarily in `temp_webm/`, convert them to Whisper-ready `.wav` files in `audio/`, and capture the source URLs under `vidLinks/`.
	 - Remove `temp_webm/` after the conversions succeed and persist the list of successfully downloaded video IDs in `downloaded_archive.txt` to skip duplicates next time.
	 - Write `failed_downloads.txt` inside the playlist folder if any items still fail after automatic retries (video ID, URL, and reason).

### Handling YouTube throttling
- The downloader already retries transient failures and randomises request pauses, but YouTube may still return HTTP 403/429 responses. When that happens:
  - Provide a cookies file (exported from a logged-in browser) named `download/cookies.txt`, or set `YTDLP_COOKIES` to its full path before running `python main.py`.
  - Re-run the download; cached playlists will skip the metadata step and resume quickly.
- Incomplete `.part` files are skipped automatically and reported in the logs so you can retry only the failed items later.

### Retrying failed downloads
- If you see `failed_downloads.txt` inside a playlist folder, YouTube rejected or throttled the listed videos even after the built-in retries.
- Wait a few minutes (or supply fresh cookies) and run the downloader again; only the missing items will be retried thanks to the download archive.
- You can delete `failed_downloads.txt` after verifying that every `.wav` file has been produced.
