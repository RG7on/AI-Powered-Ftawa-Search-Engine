from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from yt_dlp import YoutubeDL

FFMPEG_CANDIDATES: Tuple[Path, ...] = (
    Path(os.environ.get("FFMPEG_PATH", "")),
    Path("C:/ffmpeg/bin/ffmpeg.exe"),
    Path("C:/ffmpeg/ffmpeg.exe"),
)

DEFAULT_HTTP_HEADERS: Dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

EXTRACTOR_ARGS: Dict[str, Any] = {
    "youtube": {
        "player_client": ["android"]
    }
}

RETRY_SLEEP_CONFIG: Dict[str, Any] = {"min": 1, "max": 5, "factor": 1.5}

INVALID_PATH_CHARS = re.compile(r'[<>:"/\\|?*]')


class PlaylistDownloadError(RuntimeError):
    """Raised when a playlist fails to download."""


@dataclass
class PlaylistConfig:
    url: str
    name: str | None = None


@dataclass
class PlaylistFile:
    comments: List[str]
    configs: List[PlaylistConfig]


@dataclass(frozen=True)
class PlaylistOption:
    config: PlaylistConfig
    display_title: str
    entry_count: int | None = None


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def resolve_ffmpeg_path(explicit_path: str | None = None) -> Path:
    candidates: Iterable[Path]
    if explicit_path:
        candidates = (Path(explicit_path),)
    else:
        candidates = filter(None, FFMPEG_CANDIDATES)

    for candidate in candidates:
        if candidate and candidate.exists() and candidate.is_file():
            return candidate

    raise FileNotFoundError(
        "Could not locate ffmpeg executable. Set FFMPEG_PATH env var or install at C:/ffmpeg/bin/ffmpeg.exe."
    )


def sanitize_name(name: str) -> str:
    sanitized = INVALID_PATH_CHARS.sub("_", name)
    sanitized = sanitized.strip().strip(".")
    sanitized = re.sub(r"\s+", " ", sanitized)
    return sanitized or "playlist"


def friendly_title(metadata: Dict[str, Any]) -> str:
    return metadata.get("title") or metadata.get("id") or "playlist"


def parse_playlist_line(line: str) -> PlaylistConfig:
    if "|" in line:
        name_part, url_part = line.split("|", 1)
        name = name_part.strip() or None
        url = url_part.strip()
    else:
        name = None
        url = line.strip()

    if not url:
        raise ValueError("Playlist entry is missing a URL.")

    return PlaylistConfig(url=url, name=name)


def load_playlist_configs(playlists_file: Path) -> PlaylistFile:
    if not playlists_file.exists():
        raise FileNotFoundError(f"Playlists file not found: {playlists_file}")

    comments: List[str] = []
    configs: List[PlaylistConfig] = []
    for raw_line in playlists_file.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped:
            comments.append("")
            continue
        if stripped.startswith("#"):
            comments.append(raw_line.rstrip())
            continue
        configs.append(parse_playlist_line(stripped))

    if not configs:
        raise ValueError(
            f"No playlist URLs found in {playlists_file}. Add one playlist per line (lines starting with # are ignored)."
        )

    return PlaylistFile(comments=comments, configs=configs)


def save_playlist_configs(playlists_file: Path, data: PlaylistFile) -> None:
    lines: List[str] = []

    for comment in data.comments:
        lines.append(comment)

    if lines and lines[-1] != "":
        lines.append("")

    for config in data.configs:
        if config.name:
            lines.append(f"{config.name}|{config.url}")
        else:
            lines.append(config.url)

    content = "\n".join(lines) + "\n"
    playlists_file.write_text(content, encoding="utf-8")


def ensure_playlist_structure(base_dir: Path) -> Dict[str, Path]:
    temp_dir = base_dir / "temp_webm"
    audio_dir = base_dir / "audio"
    links_dir = base_dir / "vidLinks"

    for directory in (temp_dir, audio_dir, links_dir):
        directory.mkdir(parents=True, exist_ok=True)

    return {"temp": temp_dir, "audio": audio_dir, "links": links_dir}


def resolve_cookies_file() -> Path | None:
    env_path = os.environ.get("YTDLP_COOKIES") or os.environ.get("YOUTUBE_COOKIES")
    if env_path:
        path = Path(env_path).expanduser()
        if path.exists():
            return path

    default = Path(__file__).resolve().parent / "cookies.txt"
    if default.exists():
        return default
    return None


def extract_playlist_metadata(playlist_url: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {"quiet": True, "skip_download": True}

    with YoutubeDL(params) as ydl:  # type: ignore[arg-type]
        info = ydl.extract_info(playlist_url, download=False)
    if not info:
        raise PlaylistDownloadError(f"Failed to retrieve metadata for playlist: {playlist_url}")
    if info.get("_type") == "url":
        # Some playlists resolve to another URL (e.g., redirects). Extract again.
        redirected_url = info.get("url")
        if redirected_url:
            return extract_playlist_metadata(redirected_url)
    return info  # type: ignore[return-value]


def extract_playlist_overview(playlist_url: str) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "quiet": True,
        "skip_download": True,
        "extract_flat": True,
    }

    with YoutubeDL(params) as ydl:  # type: ignore[arg-type]
        info = ydl.extract_info(playlist_url, download=False)
    if not info:
        raise PlaylistDownloadError(f"Failed to retrieve overview for playlist: {playlist_url}")
    return info  # type: ignore[return-value]


def prompt_for_playlist_selection(playlists: Sequence[PlaylistOption]) -> List[PlaylistOption]:
    if not playlists:
        return []

    while True:
        print("Available playlists:")
        for idx, option in enumerate(playlists, start=1):
            label = option.display_title
            if option.entry_count:
                label = f"{label} ({option.entry_count} videos)"
            print(f"  [{idx}] {label}")
        print("  [A] All playlists")

        choice = input("\nEnter the playlist name or numbers (comma separated) to download [A]: ").strip()
        if not choice:
            choice = "a"

        if choice.lower() in {"a", "all"}:
            return list(playlists)

        parts = [part.strip() for part in choice.split(",") if part.strip()]
        selected: List[PlaylistOption] = []
        seen_indexes: set[int] = set()
        for part in parts:
            if part.isdigit():
                idx = int(part)
                if 1 <= idx <= len(playlists) and idx not in seen_indexes:
                    selected.append(playlists[idx - 1])
                    seen_indexes.add(idx)
                else:
                    print("Invalid number in selection. Try again.\n")
                    break
            else:
                lowered = part.lower()
                match = next(
                    (
                        option
                        for option in playlists
                        if option.display_title.lower() == lowered
                        or (option.config.name and option.config.name.lower() == lowered)
                    ),
                    None,
                )
                if match and match not in selected:
                    selected.append(match)
                else:
                    print("Playlist name not recognised. Try again.\n")
                    break
        else:
            if selected:
                return selected
            print("No valid playlists selected. Try again.\n")
            continue

        # If we get here due to break in for-loop, restart prompt
        continue


def download_playlist_audio(
    playlist_url: str,
    download_root: Path,
    ffmpeg_path: Path,
    metadata: Dict[str, Any] | None = None,
) -> None:
    metadata = metadata or extract_playlist_metadata(playlist_url)
    playlist_title = friendly_title(metadata)
    playlist_dir_name = sanitize_name(playlist_title)
    playlist_dir = download_root / playlist_dir_name
    logging.info("Processing playlist '%s' -> %s", playlist_title, playlist_dir)

    dirs = ensure_playlist_structure(playlist_dir)
    temp_dir = dirs["temp"]
    audio_dir = dirs["audio"]
    links_dir = dirs["links"]

    raw_entries = metadata.get("entries") or []
    entries = [entry for entry in raw_entries if entry]
    if not entries:
        logging.warning("No videos found in playlist: %s", playlist_url)
        return

    # Build map of video id -> link for later persistence
    link_map: Dict[str, str] = {}
    for entry in entries:
        video_id = entry.get("id")
        webpage_url = entry.get("webpage_url") or entry.get("url")
        if video_id and webpage_url:
            link_map[video_id] = webpage_url

    successful_ids: set[str] = set()
    failed_details: Dict[str, Dict[str, str]] = {}

    def record_failure(video_id: str, reason: str, url: str | None = None) -> None:
        if not video_id:
            return
        existing = failed_details.get(video_id, {})
        resolved_url = url or existing.get("url") or link_map.get(video_id, "")
        failed_details[video_id] = {"url": resolved_url, "reason": reason}

    def convert_source_file(source_file: Path) -> None:
        if source_file.is_dir():
            return
        if source_file.suffix == ".part":
            video_id = source_file.name.split(".")[0]
            logging.warning("Skipping incomplete download %s", source_file.name)
            record_failure(video_id, "partial download detected (yt-dlp interruption)")
            source_file.unlink(missing_ok=True)
            return

        video_id = source_file.stem
        output_file = audio_dir / f"{video_id}.wav"
        try:
            convert_to_wav(source_file, output_file, ffmpeg_path)
            successful_ids.add(video_id)
            failed_details.pop(video_id, None)
            link = link_map.get(video_id)
            if link:
                (links_dir / f"{video_id}.txt").write_text(link + "\n", encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            record_failure(video_id, f"conversion failed: {exc}")
        finally:
            source_file.unlink(missing_ok=True)

    def convert_all_temp_files() -> None:
        for candidate in list(temp_dir.glob("*")):
            convert_source_file(candidate)

    # Download best available audio into temp directory
    cookies_file = resolve_cookies_file()
    download_archive = playlist_dir / "downloaded_archive.txt"

    ydl_opts: Dict[str, Any] = {
        "quiet": False,
        "format": "bestaudio/best",
        "outtmpl": str(temp_dir / "%(id)s.%(ext)s"),
        "ignoreerrors": True,
        "noplaylist": False,
        "retries": 5,
        "fragment_retries": 5,
        "retry_sleep": RETRY_SLEEP_CONFIG,
        "sleep_interval_requests": (1, 3),
        "http_headers": DEFAULT_HTTP_HEADERS,
        "extractor_args": EXTRACTOR_ARGS,
        "nocheckcertificate": True,
        "download_archive": str(download_archive),
    }

    if cookies_file:
        logging.info("Using cookies file %s", cookies_file)
        ydl_opts["cookiefile"] = str(cookies_file)

    logging.info("Downloading audio tracks to %s", temp_dir)
    attempt = 0
    while True:
        attempt += 1
        try:
            with YoutubeDL(ydl_opts) as ydl:  # type: ignore[arg-type]
                return_code = ydl.download([playlist_url])
        except Exception as exc:  # noqa: BLE001
            if attempt >= 3:
                raise
            wait = min(10, 2 * attempt)
            logging.warning("Retrying playlist download due to error: %s. Retrying in %s seconds", exc, wait)
            time.sleep(wait)
            continue

        if return_code == 0:
            break

        if attempt >= 3:
            logging.error("yt-dlp returned non-zero exit code after %s attempts", attempt)
            break

        wait = min(10, 2 * attempt)
        logging.warning("yt-dlp returned code %s, retrying in %s seconds", return_code, wait)
        time.sleep(wait)

    convert_all_temp_files()

    pending_ids = [video_id for video_id in link_map if video_id not in successful_ids]
    if pending_ids:
        logging.warning(
            "Detected %s videos without completed audio after first pass. Retrying individually.",
            len(pending_ids),
        )
        retry_opts: Dict[str, Any] = dict(ydl_opts)
        retry_opts["ignoreerrors"] = False
        retry_opts["noplaylist"] = True
        retry_opts["force_overwrites"] = True

        for video_id in pending_ids:
            url = link_map.get(video_id)
            if not url:
                record_failure(video_id, "missing URL in metadata")
                continue

            logging.info("Retrying download for %s", video_id)
            try:
                with YoutubeDL(retry_opts) as ydl:  # type: ignore[arg-type]
                    ydl.download([url])
                convert_all_temp_files()
            except Exception as exc:  # noqa: BLE001
                record_failure(video_id, f"individual retry failed: {exc}", url=url)
                wait = min(10, 2)
                time.sleep(wait)

    remaining_ids = [video_id for video_id in link_map if video_id not in successful_ids]
    for video_id in remaining_ids:
        if video_id not in failed_details:
            record_failure(video_id, "no audio file produced after retries")

    total_videos = len(link_map)
    logging.info("Finished processing playlist. Successful audio files: %s/%s", len(successful_ids), total_videos)

    failed_report = playlist_dir / "failed_downloads.txt"
    if failed_details:
        lines = [
            "The following videos failed to download or convert:",
            "",
            "Video ID | URL | Reason",
            "---------------------------------------------",
        ]
        for video_id, detail in sorted(failed_details.items()):
            lines.append(f"{video_id} | {detail.get('url', '')} | {detail.get('reason', 'unknown')}")
        lines.append("")
        lines.append(
            "Retry the downloader once the throttling subsides. Videos listed here will be attempted again on the next run."
        )
        failed_report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logging.warning("Some videos failed to process. See %s for details.", failed_report)
    elif failed_report.exists():
        failed_report.unlink()

    # Clean up temporary downloads
    logging.info("Cleaning up temporary directory %s", temp_dir)
    shutil.rmtree(temp_dir, ignore_errors=True)


def convert_to_wav(source: Path, destination: Path, ffmpeg_path: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(ffmpeg_path),
        "-y",
        "-i",
        str(source),
        "-ar",
        "16000",
        "-ac",
        "1",
        str(destination),
    ]

    logging.info("Converting %s -> %s", source.name, destination.name)
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        logging.error("ffmpeg failed for %s: %s", source, result.stderr)
        raise PlaylistDownloadError(f"ffmpeg conversion failed for {source}")


def run(playlists_path: Path | None = None, download_root: Path | None = None, ffmpeg_override: str | None = None) -> None:
    configure_logging()

    playlists_path = playlists_path or Path(__file__).with_name("playlists")
    download_root = download_root or Path(__file__).parent
    ffmpeg_path = resolve_ffmpeg_path(ffmpeg_override)

    logging.info("Using ffmpeg at %s", ffmpeg_path)

    playlist_file = load_playlist_configs(playlists_path)

    options: List[PlaylistOption] = []
    updated = False
    for config in playlist_file.configs:
        display_title = config.name or config.url
        entry_count: int | None = None

        if config.name is None:
            try:
                overview = extract_playlist_overview(config.url)
                display_title = overview.get("title") or display_title
                entries = overview.get("entries")
                if isinstance(entries, list):
                    entry_count = len([entry for entry in entries if entry])
                elif isinstance(overview.get("playlist_count"), int):
                    entry_count = int(overview["playlist_count"])
                config.name = display_title
                updated = True
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "Unable to fetch playlist title for %s, using URL instead: %s",
                    config.url,
                    exc,
                )

        options.append(PlaylistOption(config=config, display_title=display_title, entry_count=entry_count))

    if updated:
        save_playlist_configs(playlists_path, playlist_file)

    if not options:
        logging.error("No valid playlists available to download.")
        return

    selections = prompt_for_playlist_selection(options)
    if not selections:
        logging.info("No playlists selected. Nothing to download.")
        return

    for option in selections:
        config = option.config
        logging.info("Selected playlist: %s", option.display_title)
        try:
            download_playlist_audio(config.url, download_root, ffmpeg_path, metadata=None)
        except Exception as exc:  # noqa: BLE001
            logging.error("Failed to process playlist %s: %s", config.url, exc)


if __name__ == "__main__":
    run()
