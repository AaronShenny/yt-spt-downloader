#https://chatgpt.com/c/694e1afa-55d0-8320-9296-8e4e9b4670b1
import sys
from yt_dlp import YoutubeDL
import os
import re
import time
from typing import Optional, List, Dict, Tuple
from urllib.parse import urlparse, parse_qs
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache

MAX_RETRIES = 3
RETRY_DELAY = 2
MAX_CONCURRENT_WORKERS = 5
DEFAULT_CONCURRENT_WORKERS = 3


@lru_cache(maxsize=128)
def get_url_info(url: str) -> Tuple[str, Dict]:
    try:
        ydl_opts = {
            "quiet": True,
            "extract_flat": True,
            "no_warnings": True,
            "skip_download": True,
            "playlist_items": "1",
        }

        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info is None:
                parsed = urlparse(url)
                q = parse_qs(parsed.query)

                if "/@" in url or "/channel/" in url or "/c/" in url or "/user/" in url:
                    return "channel", {}
                elif "list" in q:
                    return "playlist", {}
                else:
                    return "video", {}

            ctype = info.get("_type", "video")

            if ctype == "playlist":
                if info.get("uploader_id") and (
                    "/@" in url or "/channel/" in url or "/c/" in url or "/user/" in url
                ):
                    return "channel", info
                return "playlist", info

            return ctype, info

    except Exception:
        parsed = urlparse(url)
        q = parse_qs(parsed.query)

        if "/@" in url or "/channel/" in url or "/c/" in url or "/user/" in url:
            return "channel", {}
        elif "list" in q:
            return "playlist", {}
        else:
            return "video", {}


def get_content_type(url: str) -> str:
    c, _ = get_url_info(url)
    return c


def parse_multiple_urls(input_string: str) -> List[str]:
    urls = re.split(r"[,\s\n\t]+", input_string.strip())
    urls = [u.strip() for u in urls if u.strip()]

    valid = []
    invalid = 0

    for url in urls:
        if ("youtube.com" in url or "youtu.be" in url) and (
            "/watch?" in url
            or "/playlist?" in url
            or "/@"
            in url
            or "/channel/" in url
            or "/c/" in url
            or "/user/" in url
            or "youtu.be/" in url
        ):
            valid.append(url)
        else:
            print(f"⚠️  Skipping invalid URL: {url}")
            invalid += 1

    if invalid > 0:
        print(
            f"💡 Found {len(valid)} valid YouTube URLs, skipped {invalid} invalid entries"
        )

    return valid


def get_available_formats(url: str) -> None:
    try:
        with YoutubeDL({"listformats": True}) as ydl:
            ydl.extract_info(url, download=False)
    except Exception as e:
        print(f"Error listing formats: {e}")


# ✔ QUALITY SELECTOR
def get_format_for_quality(quality: str, audio_only: bool) -> Tuple[str, str]:
    if audio_only:
        return "bestaudio/best", "mp3"

    quality_map = {
        "144": "bestvideo[height<=144]+bestaudio/best/best[height<=144]",
        "240": "bestvideo[height<=240]+bestaudio/best/best[height<=240]",
        "360": "bestvideo[height<=360]+bestaudio/best/best[height<=360]",
        "480": "bestvideo[height<=480]+bestaudio/best/best[height<=480]",
        "720": "bestvideo[height<=720]+bestaudio/best/best[height<=720]",
        "1080": "bestvideo[height<=1080]+bestaudio/best/best[height<=1080]",
        "1440": "bestvideo[height<=1440]+bestaudio/best/best[height<=1440]",
        "2160": "bestvideo[height<=2160]+bestaudio/best/best[height<=2160]",
    }

    return quality_map.get(quality, "bestvideo+bestaudio/best"), "mp4"


def download_single_video(
    url: str,
    output_path: str,
    thread_id: int = 0,
    audio_only: bool = False,
    quality: str = "1080",
) -> dict:

    format_selector, ext = get_format_for_quality(quality, audio_only)

    if audio_only:
        postprocessors = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ]
        print(f"🎵 [Thread {thread_id}] MP3 mode enabled")
    else:
        postprocessors = [{"key": "FFmpegVideoConvertor", "preferedformat": "mp4"}]

    opts = {
        "format": format_selector,
        "postprocessors": postprocessors,
        "retries": MAX_RETRIES,
        "fragment_retries": MAX_RETRIES,
        "noplaylist": False,
        "merge_output_format": "mp4",
    }

    ctype, _ = get_url_info(url)

    if ctype == "playlist":
        print(f"📋 [Thread {thread_id}] Playlist detected — downloading all videos")
        opts["outtmpl"] = os.path.join(
            output_path, "%(playlist_title)s", f"%(playlist_index)s-%(title)s.{ext}"
        )
    elif ctype == "channel":
        print(f"📺 [Thread {thread_id}] Channel detected — downloading uploads")
        opts["outtmpl"] = os.path.join(
            output_path, "%(uploader)s", f"%(upload_date)s-%(title)s.{ext}"
        )
    else:
        print(f"🎥 [Thread {thread_id}] Single video")
        opts["outtmpl"] = os.path.join(output_path, f"%(title)s.{ext}")

    last = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with YoutubeDL(opts) as ydl:
                result = ydl.extract_info(url, download=True)

            if result is None:
                return {
                    "url": url,
                    "success": False,
                    "message": f"❌ [Thread {thread_id}] Could not extract information",
                }

            title = result.get("title", "Unknown")
            return {
                "url": url,
                "success": True,
                "message": f"✅ [Thread {thread_id}] '{title}' finished",
            }

        except Exception as e:
            last = e
            if attempt < MAX_RETRIES:
                delay = RETRY_DELAY * (2 ** (attempt - 1))
                print(
                    f"⚠️  [Thread {thread_id}] Attempt {attempt}/{MAX_RETRIES} failed. Retrying in {delay}s..."
                )
                time.sleep(delay)
            else:
                return {
                    "url": url,
                    "success": False,
                    "message": f"❌ [Thread {thread_id}] Failed: {last}",
                }


def download_youtube_content(
    urls: List[str],
    output_path: Optional[str] = None,
    max_workers: int = DEFAULT_CONCURRENT_WORKERS,
    audio_only: bool = False,
    quality: str = "1080",
):
    if output_path is None:
        output_path = os.path.join(os.getcwd(), "downloads")

    os.makedirs(output_path, exist_ok=True)

    playlist_count = sum(1 for u in urls if get_content_type(u) == "playlist")
    channel_count = sum(1 for u in urls if get_content_type(u) == "channel")
    video_count = len(urls) - playlist_count - channel_count

    print("\n🚀 Starting downloads")
    print(f"📁 Output: {output_path}")
    print(f"🎧 Mode: {'MP3 Audio' if audio_only else 'MP4 Video'}")
    if not audio_only:
        print(f"🎞 Quality: {quality}p")
    print(
        f"📋 Content: {playlist_count} playlists | {channel_count} channels | {video_count} videos"
    )
    print("-" * 60)

    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                download_single_video, url, output_path, i + 1, audio_only, quality
            ): url
            for i, url in enumerate(urls)
        }

        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            print(res["message"])

    print("\n" + "=" * 60)
    print("📊 DOWNLOAD SUMMARY")
    print("=" * 60)

    success = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]

    print(f"✅ Success: {len(success)}")
    print(f"❌ Failed: {len(failed)}")

    if failed:
        print("\n⚠️ Failed items:")
        for r in failed:
            print(f" • {r['url']}")
            print(f"   Reason: {r['message']}")


if __name__ == "__main__":
    print("📥 YouTube Multi-Content Downloader")
    print("=" * 50)
    print("Supported input:")
    print("  • Single URL")
    print("  • Comma-separated list")
    print("  • Spaces")
    print("  • Multiple lines")
    print("-" * 50)

    user_input = input("Enter YouTube URL(s): ")

    if not user_input.strip():
        print("❌ No URLs entered")
        sys.exit()

    urls = parse_multiple_urls(user_input)

    format_choice = input(
        "\nChoose format:\n  1. MP4 Video\n  2. MP3 Audio\n> "
    ).strip()

    audio_only = format_choice == "2"

    quality = "1080"
    if not audio_only:
        quality = input(
            "\nChoose quality (144–2160, default 1080): "
        ).strip() or "1080"

    workers = DEFAULT_CONCURRENT_WORKERS
    if len(urls) > 1:
        try:
            workers = int(
                input(
                    f"\nConcurrent downloads (1–{MAX_CONCURRENT_WORKERS}, default {DEFAULT_CONCURRENT_WORKERS}): "
                )
                or DEFAULT_CONCURRENT_WORKERS
            )
            workers = max(1, min(MAX_CONCURRENT_WORKERS, workers))
        except:
            workers = DEFAULT_CONCURRENT_WORKERS

    download_youtube_content(urls, max_workers=workers, audio_only=audio_only, quality=quality)
