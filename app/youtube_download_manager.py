"""A friendly interactive downloader for YouTube videos and playlists you may save."""

from __future__ import annotations

import os
import shutil
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from rich.console import Console
from rich.progress import BarColumn, DownloadColumn, Progress, TextColumn, TimeRemainingColumn, TransferSpeedColumn
from rich.table import Table

console = Console(force_terminal=True, force_interactive=True)


def human_size(value: Any) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return "Size unavailable"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}"
        size /= 1024
    return "Size unavailable"


def is_youtube_url(url: str) -> bool:
    host = urlparse(url).netloc.lower().split(":")[0]
    return host in {"youtube.com", "youtu.be"} or host.endswith(".youtube.com") or host.endswith(".youtu.be")


def pick_folder() -> Path | None:
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        selected = filedialog.askdirectory(title="Choose where to save your downloads")
        root.destroy()
        if selected:
            return Path(selected)
    except Exception:
        pass
    answer = input("Paste a folder path (or press Enter to cancel): ").strip().strip('"')
    return Path(answer) if answer else None


def ffmpeg_location() -> str | None:
    launcher_location = os.environ.get("YTDL_FFMPEG_LOCATION")
    if launcher_location and (Path(launcher_location) / "ffmpeg.exe").is_file():
        return launcher_location
    executable = shutil.which("ffmpeg")
    return str(Path(executable).parent) if executable else None


def extract_info(url: str) -> dict[str, Any]:
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "extract_flat": False}) as ydl:
        return ydl.extract_info(url, download=False)


def get_sample(info: dict[str, Any]) -> dict[str, Any]:
    if info.get("_type") != "playlist":
        return info
    entries = [entry for entry in info.get("entries", []) if entry]
    if not entries:
        raise ValueError("This playlist has no downloadable videos.")
    return entries[0]


def quality_choices(video: dict[str, Any]) -> list[dict[str, Any]]:
    formats = video.get("formats") or []
    audio = [item for item in formats if item.get("vcodec") == "none" and item.get("acodec") not in (None, "none")]
    best_audio = max(audio, key=lambda item: (item.get("abr") or 0, item.get("filesize") or item.get("filesize_approx") or 0), default=None)
    audio_bytes = (best_audio or {}).get("filesize") or (best_audio or {}).get("filesize_approx") or 0
    by_height: dict[int, dict[str, Any]] = {}
    for item in formats:
        height = item.get("height")
        if not height or item.get("vcodec") in (None, "none"):
            continue
        previous = by_height.get(height)
        score = (item.get("tbr") or 0, item.get("filesize") or item.get("filesize_approx") or 0)
        prior_score = ((previous or {}).get("tbr") or 0, (previous or {}).get("filesize") or (previous or {}).get("filesize_approx") or 0)
        if previous is None or score > prior_score:
            by_height[height] = item
    choices: list[dict[str, Any]] = []
    for height in sorted(by_height, reverse=True):
        item = by_height[height]
        video_bytes = item.get("filesize") or item.get("filesize_approx") or 0
        has_audio = item.get("acodec") not in (None, "none")
        choices.append({
            "height": height,
            "format_id": item.get("format_id"),
            "audio_id": None if has_audio or not best_audio else best_audio.get("format_id"),
            "extension": item.get("ext", "video"),
            "size": video_bytes if has_audio else video_bytes + audio_bytes,
            "needs_merge": not has_audio,
        })
    return choices


def show_choices(choices: list[dict[str, Any]]) -> None:
    table = Table(title="Available qualities")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Quality", style="bold")
    table.add_column("Estimated download", justify="right")
    table.add_column("Details")
    for index, choice in enumerate(choices, 1):
        details = choice["extension"].upper() + (" + best audio" if choice["needs_merge"] else "")
        table.add_row(str(index), f"{choice['height']}p", human_size(choice["size"]), details)
    console.print(table)
    console.print("[dim]Sizes are estimates supplied by YouTube and can vary.[/dim]")


def playlist_plan(info: dict[str, Any], maximum_height: int) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for index, entry in enumerate((item for item in info.get("entries", []) if item), 1):
        available = [choice for choice in quality_choices(entry) if choice["height"] <= maximum_height]
        selected = available[0] if available else None
        fallback = f"https://www.youtube.com/watch?v={entry.get('id', '')}"
        plan.append({
            "index": index,
            "title": entry.get("title", f"Video {index}"),
            "quality": f"{selected['height']}p" if selected else "Unavailable",
            "size": selected["size"] if selected else None,
            "id": entry.get("id", ""),
            "url": entry.get("webpage_url") or entry.get("original_url") or fallback,
        })
    return plan


def show_playlist_plan(plan: list[dict[str, Any]]) -> None:
    table = Table(title=f"Playlist download plan - {len(plan)} videos")
    table.add_column("#", justify="right", style="cyan")
    table.add_column("Video")
    table.add_column("Quality")
    table.add_column("Estimated size", justify="right")
    total, unavailable = 0, 0
    for item in plan:
        if isinstance(item["size"], (int, float)) and item["size"] > 0:
            total += item["size"]
        else:
            unavailable += 1
        table.add_row(str(item["index"]), item["title"][:72], item["quality"], human_size(item["size"]))
    console.print(table)
    note = f" ({unavailable} size estimate unavailable)" if unavailable else ""
    console.print(f"[bold]Estimated playlist total: {human_size(total)}[/bold]{note}\n")


def existing_video_ids(folder: Path, video_ids: list[str]) -> set[str]:
    """Find completed files previously saved by this app for the same YouTube IDs."""
    completed_extensions = {".mp4", ".webm", ".mkv", ".mov"}
    found: set[str] = set()
    files = list(folder.iterdir()) if folder.is_dir() else []
    for video_id in video_ids:
        marker = f" [{video_id}]."
        if any(marker in path.name and path.suffix.lower() in completed_extensions for path in files):
            found.add(video_id)
    return found


def choose_existing_action(existing_count: int) -> str:
    while True:
        choice = input(f"{existing_count} video(s) already exist here. [S]kip, [O]verwrite, or [C]ancel: ").strip().lower()
        if choice in {"s", "skip"}:
            return "skip"
        if choice in {"o", "overwrite"}:
            return "overwrite"
        if choice in {"c", "cancel", ""}:
            return "cancel"
        console.print("[red]Enter S, O, or C.[/red]")


class LiveProgress:
    def __init__(self, total_videos: int | None = None) -> None:
        self.progress = Progress(
            TextColumn("[bold cyan]{task.description}[/bold cyan]"), BarColumn(bar_width=32),
            TextColumn("{task.percentage:>5.1f}%"), DownloadColumn(), TransferSpeedColumn(), TimeRemainingColumn(),
            console=console, refresh_per_second=8,
        )
        self.total_videos = total_videos
        self.current_task: int | None = None
        self.overall_task = self.progress.add_task(f"Playlist 0/{total_videos}", total=total_videos) if total_videos else None
        self.current_video_id: str | None = None
        self.started_videos = 0
        self.completed_videos = 0

    def start_video(self, index: int = 1) -> None:
        label = f"Video {index}/{self.total_videos}" if self.total_videos else "Downloading"
        if self.current_task is None:
            self.current_task = self.progress.add_task(label, total=None)
        else:
            self.progress.update(self.current_task, description=label, completed=0, total=None)

    def complete_video(self, index: int) -> None:
        if self.current_task is not None:
            total = self.progress.tasks[self.current_task].total
            if total:
                self.progress.update(self.current_task, completed=total)
        if self.overall_task is not None and self.total_videos:
            self.progress.update(self.overall_task, completed=index, description=f"Playlist {index}/{self.total_videos}")

    def track_playlist_video(self, info: dict[str, Any]) -> None:
        video_id = info.get("id")
        if not video_id or video_id == self.current_video_id:
            return
        if self.current_video_id is not None:
            self.completed_videos += 1
            self.complete_video(self.completed_videos)
        self.current_video_id = video_id
        self.started_videos += 1
        self.start_video(self.started_videos)
        console.print(f"[dim]Starting {self.started_videos}/{self.total_videos}: {info.get('title', 'Video')[:76]}[/dim]")

    def finish_playlist(self) -> None:
        if self.current_video_id is not None and self.completed_videos < self.started_videos:
            self.completed_videos += 1
            self.complete_video(self.completed_videos)

    def hook(self, update: dict[str, Any]) -> None:
        if update.get("status") != "downloading":
            return
        if self.total_videos:
            self.track_playlist_video(update.get("info_dict") or {})
        total = update.get("total_bytes") or update.get("total_bytes_estimate")
        downloaded = update.get("downloaded_bytes", 0)
        if self.current_task is None:
            self.current_task = self.progress.add_task("Downloading", total=total or None)
        self.progress.update(self.current_task, completed=downloaded, total=total or None)


class FriendlyYtdlpLogger:
    """Prevent yt-dlp from printing duplicate raw errors the UI already handles."""

    def debug(self, message: str) -> None:
        pass

    def warning(self, message: str) -> None:
        pass

    def error(self, message: str) -> None:
        pass


def download(url: str, selected: dict[str, Any], folder: Path, plan: list[dict[str, Any]] | None = None, overwrite: bool = False) -> bool:
    installed_ffmpeg = ffmpeg_location()
    if selected["needs_merge"] and not installed_ffmpeg:
        console.print("[yellow]FFmpeg was not found. Nothing was downloaded.[/yellow]")
        return False
    if plan is not None:
        selector = f"bv*[height<={selected['height']}]+ba/b[height<={selected['height']}]"
    elif selected["audio_id"]:
        selector = f"{selected['format_id']}+{selected['audio_id']}"
    else:
        selector = str(selected["format_id"])
    fallback_selector = f"b[height<={selected['height']}]/b"
    live = LiveProgress(len(plan) if plan is not None else None)
    options: dict[str, Any] = {
        "format": selector,
        "outtmpl": str(folder / ("%(playlist_title)s/%(playlist_index)03d - %(title)s [%(id)s].%(ext)s" if plan is not None else "%(title)s [%(id)s].%(ext)s")),
        "noplaylist": plan is None,
        "merge_output_format": "mp4", "progress_hooks": [live.hook], "quiet": True, "no_warnings": True,
        "logger": FriendlyYtdlpLogger(), "ignoreerrors": plan is not None,
        "windowsfilenames": True, "continuedl": not overwrite, "overwrites": overwrite,
        "concurrent_fragment_downloads": 8,
    }
    if installed_ffmpeg:
        options["ffmpeg_location"] = installed_ffmpeg
    if plan is not None:
        options["playlist_items"] = ",".join(str(item["index"]) for item in plan)
    folder.mkdir(parents=True, exist_ok=True)

    def download_with_retry(target_url: str) -> None:
        # A fresh extraction can recover from short-lived URLs. If YouTube still
        # rejects the stream, Safari's HLS client is a compatible fallback that
        # can work when the default client requires a missing playback token.
        profiles = [None, {"youtube": {"player_client": ["web_safari"]}}]
        for profile_index, extractor_args in enumerate(profiles):
            try:
                active_options = options.copy()
                if extractor_args:
                    active_options["extractor_args"] = extractor_args
                    # The fallback client has its own formats, so format IDs from
                    # the original client may not exist. Use the best compatible
                    # stream at or below the quality the user chose instead.
                    active_options["format"] = fallback_selector
                    console.print("[yellow]Trying YouTube's compatible playback fallback...[/yellow]")
                with yt_dlp.YoutubeDL(active_options) as ydl:
                    ydl.download([target_url])
                return
            except yt_dlp.utils.DownloadError:
                if profile_index:
                    raise
                console.print("[yellow]YouTube rejected that stream. Trying a compatible fallback...[/yellow]")

    with live.progress:
        if plan is None:
            live.start_video()
            download_with_retry(url)
        else:
            download_with_retry(url)
            live.finish_playlist()
    return True


def main() -> None:
    console.print("\n[bold cyan]YouTube Download Manager[/bold cyan]")
    console.print("Download videos and playlists only when you have permission to save them.\n")
    while True:
        kind = input("Choose download type: [1] Single video  [2] Playlist  (or Q to quit): ").strip().lower()
        if kind in {"q", "quit", "exit"}:
            return
        if kind not in {"1", "2"}:
            console.print("[red]Choose 1 for a video or 2 for a playlist.[/red]")
            continue
        wanted_playlist = kind == "2"
        url = input("Paste the YouTube playlist link: " if wanted_playlist else "Paste the YouTube video link: ").strip()
        if not url:
            continue
        if not is_youtube_url(url):
            console.print("[red]That is not a YouTube link. Paste a youtube.com or youtu.be link.[/red]")
            continue
        try:
            with console.status("Checking the YouTube link and loading qualities...", spinner="dots"):
                info = extract_info(url)
                is_playlist = info.get("_type") == "playlist"
                if is_playlist != wanted_playlist:
                    actual = "playlist" if is_playlist else "single video"
                    console.print(f"[yellow]This link is a {actual}. Choose the matching option and try again.[/yellow]")
                    continue
                sample = get_sample(info)
                choices = quality_choices(sample)
            if not choices:
                console.print("[red]No video qualities were available for this link.[/red]")
                continue
            if is_playlist:
                count = len([item for item in info.get("entries", []) if item])
                console.print(f"\n[bold]{info.get('title', 'Playlist')}[/bold] - {count} videos")
                console.print(f"Qualities below are based on: [italic]{sample.get('title', 'first video')}[/italic]")
            else:
                console.print(f"\n[bold]{sample.get('title', 'Video')}[/bold]")
            show_choices(choices)
            raw_choice = input("Choose a quality number (or press Enter to cancel): ").strip()
            if not raw_choice:
                continue
            selected = choices[int(raw_choice) - 1]
            plan = playlist_plan(info, selected["height"]) if is_playlist else None
            if plan:
                show_playlist_plan(plan)
            folder = pick_folder()
            if not folder:
                console.print("[yellow]Download cancelled.[/yellow]")
                continue
            video_ids = [item["id"] for item in plan] if plan is not None else [sample.get("id", "")]
            existing = existing_video_ids(folder, [video_id for video_id in video_ids if video_id])
            overwrite = False
            if existing:
                action = choose_existing_action(len(existing))
                if action == "cancel":
                    console.print("[yellow]Download cancelled.[/yellow]")
                    continue
                if action == "skip":
                    if plan is None:
                        console.print("[yellow]Existing download kept; nothing to download.[/yellow]")
                        continue
                    plan = [item for item in plan if item["id"] not in existing]
                    if not plan:
                        console.print("[yellow]All playlist videos already exist; nothing to download.[/yellow]")
                        continue
                    console.print(f"[yellow]Skipping {len(existing)} existing video(s).[/yellow]")
                else:
                    overwrite = True
            console.print(f"Saving to: [cyan]{folder}[/cyan]")
            if download(url, selected, folder, plan, overwrite):
                console.print("[green]Download complete.[/green]\n")
        except (ValueError, IndexError):
            console.print("[red]Please choose one of the listed quality numbers.[/red]")
        except yt_dlp.utils.DownloadError as error:
            console.print(f"[red]Download error:[/red] {error}")
        except KeyboardInterrupt:
            console.print("\n[yellow]Download cancelled.[/yellow]")


if __name__ == "__main__":
    main()
