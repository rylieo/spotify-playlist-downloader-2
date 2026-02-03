import os
import argparse
import traceback
import time
from tempfile import NamedTemporaryFile
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Semaphore, Event
from tqdm import tqdm

from src.spotify_fetcher import fetch_playlist
from src.metadata_cleaner import clean_metadata
from src.search_engine import build_query
from src.downloader import download_audio
from src.encoder import encode_mp3
from src.tagger import tag_audio
from src.utils import process_cover, sanitize_filename


# Daftar track yang bermasalah untuk diskip jika terus gagal
problematic_tracks = set()

def process_track(
    t,
    ffmpeg_sem,
    quiet=False,
    verbose=False,
    no_fallback=False,
    force=False,
    use_official=True,
    search_count=5,
    source="youtube",
    download_format="aac",
    download_bitrate_k=192,
    encode_timeout=300,
    max_retries=2,
    stop_event=None,
):
    # Cooperative cancellation: abort quickly when the stop_event is set
    if stop_event is not None and stop_event.is_set():
        raise KeyboardInterrupt()

    # Heartbeat / timing
    start_time = time.time()
    tqdm.write(f"[{t['track_number']:02d}] START: {t['artist']} - {t['title']}")
    # Cooperative cancellation: abort quickly when the stop_event is set
    if stop_event is not None and stop_event.is_set():
        raise KeyboardInterrupt()
    base = f'{t["track_number"]:02d} - {t["artist"]} - {t["title"]}'
    safe_base = sanitize_filename(base)

    # Choose extension based on requested download format
    ext = (
        "m4a"
        if download_format == "aac"
        else ("ogg" if download_format == "ogg" else "mp3")
    )
    outfilename = f"{safe_base}.{ext}"
    mp3 = os.path.join("output", "playlist", outfilename)
    cover = f'assets/covers/{t["track_number"]}.jpg'

    # If already exists and not forced, check for any existing file matching artist+title to avoid duplicates
    if not force:
        search_key = sanitize_filename(f"{t['artist']} - {t['title']}")
        existing = None
        for fname in os.listdir("output/playlist"):
            if search_key.lower() in fname.lower():
                candidate = os.path.join("output/playlist", fname)
                try:
                    if os.path.getsize(candidate) > 1024:
                        existing = candidate
                        break
                except OSError:
                    continue
        if existing:
            tqdm.write(
                f"[{t['track_number']:02d}] Skipping (already exists): {existing}"
            )
            return (t["track_number"], True, "skipped")

    with NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
        wav = tmp.name  # Variable name kept as 'wav' for consistency with rest of code

    try:
        if not quiet:
            tqdm.write(f"[{t['track_number']:02d}] Downloading: {base}")
        process_cover(t["cover_url"], cover)
        q = build_query(t, use_official=use_official)
        if stop_event is not None and stop_event.is_set():
            raise KeyboardInterrupt()
        download_audio(
            q,
            wav,
            duration_ms=t.get("duration_ms"),
            no_fallback=no_fallback,
            verbose=verbose,
            search_count=search_count,
            use_official=use_official,
            stop_event=stop_event,
        )

        # Verify the downloaded audio exists and is valid
        if stop_event is not None and stop_event.is_set():
            raise KeyboardInterrupt()
        if not (os.path.exists(wav) and os.path.getsize(wav) > 1024):
            raise RuntimeError(f"Downloaded audio missing or invalid: {wav}")

        # Move the downloaded file to the final destination
        import shutil
        shutil.move(wav, mp3)

        # Tag immediately after successful download
        try:
            if not quiet:
                tqdm.write(f"[{t['track_number']:02d}] Tagging: {mp3}")
            tag_audio(mp3, t, cover)
            # remove cover used for this track after successful tagging
            try:
                if cover and os.path.exists(cover):
                    os.remove(cover)
            except Exception as e:
                if not quiet:
                    tqdm.write(f"Failed to remove cover {cover}: {e}")

            duration = time.time() - start_time
            if not quiet:
                tqdm.write(
                    f"[{t['track_number']:02d}] DONE in {duration:.1f}s: {t['artist']} - {t['title']}"
                )

            # Log processing duration for analysis
            if duration > 120:  # If processing takes more than 2 minutes
                tqdm.write(
                    f"[{t['track_number']:02d}] WARNING: Long processing time ({duration:.1f}s) - possibly problematic"
                )

            return (
                t["track_number"],
                True,
                {"mp3": mp3, "meta": t, "cover": cover, "skipped": False},
            )
        except Exception as e:
            return (t["track_number"], False, str(e) + "\n" + traceback.format_exc())
    except Exception as e:
        try:
            os.remove(wav)
        except Exception:
            pass
        try:
            if os.path.exists(mp3):
                os.remove(mp3)
        except Exception:
            pass
        return (t["track_number"], False, str(e) + "\n" + traceback.format_exc())


def main():
    parser = argparse.ArgumentParser(description="Spotify playlist downloader")
    parser.add_argument("playlist", nargs="?", help="Spotify playlist URL")
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=min(4, (os.cpu_count() or 1) * 2),
        help="download worker threads (default: auto)",
    )
    parser.add_argument(
        "--ffmpeg-workers",
        type=int,
        default=max(1, (os.cpu_count() or 1) // 2),  # Gunakan setengah dari jumlah core CPU
        help="concurrent ffmpeg encodes",
    )
    parser.add_argument("--quiet", action="store_true", help="less verbose output")
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="do not use yt_dlp Python fallback; require yt-dlp executable",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="show verbose external tool output"
    )
    parser.add_argument(
        "--force", action="store_true", help="re-download and overwrite existing files"
    )
    parser.add_argument(
        "--no-official",
        action="store_true",
        help="do not append 'official audio' to search queries",
    )
    parser.add_argument(
        "--search-count",
        type=int,
        default=5,
        help="number of search candidates to evaluate (default: 5)",
    )
    parser.add_argument(
        "--source",
        choices=["youtube", "ytmusic"],
        default="youtube",
        help="preferred search source: 'youtube' or 'ytmusic' (YouTube Music)",
    )

    parser.add_argument(
        "--download-format",
        choices=["aac", "mp3", "ogg"],
        default="mp3",
        help="format for saved downloads (default: mp3)",
    )
    parser.add_argument(
        "--download-bitrate",
        type=int,
        default=192,
        help="target bitrate in kbps for saved downloads (default: 192)",
    )

    parser.add_argument(
        "--encode-timeout",
        type=int,
        default=300,
        help="encoding timeout per track in seconds (default: 300)",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=2,
        help="number of retries for encoding or candidate downloads before skipping (default: 2)",
    )

    args = parser.parse_args()

    playlist_url = args.playlist or input("Spotify playlist URL: ")

    raw = fetch_playlist(playlist_url)
    # fetch_playlist now returns (tracks, playlist_name)
    if isinstance(raw, tuple) or isinstance(raw, list):
        tracks, playlist_name = raw
    else:
        tracks = raw
        playlist_name = "playlist"

    tracks = clean_metadata(tracks)

    os.makedirs("assets/covers", exist_ok=True)
    os.makedirs("output/playlist", exist_ok=True)

    ffmpeg_sem = Semaphore(args.ffmpeg_workers)

    # Event used for cooperative cancellation on Ctrl+C
    stop_event = Event()

    failures = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(
                process_track,
                t,
                ffmpeg_sem,
                args.quiet,
                args.verbose,
                args.no_fallback,
                args.force,
                not args.no_official,
                args.search_count,
                args.source,
                args.download_format,
                args.download_bitrate,
                args.encode_timeout,
                args.max_retries,
                stop_event,
            ): t
            for t in tracks
        }

        with tqdm(total=len(tracks), desc="Tracks", unit="track") as pbar:
            try:
                for fut in as_completed(futures):
                    try:
                        tn, ok, info = fut.result()
                    except Exception as e:
                        # If a worker raised KeyboardInterrupt via our cooperative stop, handle it
                        tqdm.write(f"[ERROR] Worker failed: {e}")
                        failures.append((None, str(e)))
                        pbar.update(1)
                        continue

                    if not ok:
                        failures.append((tn, info))
                        tqdm.write(f"[ERROR] Track {tn}: {info}")
                    else:
                        if info == "skipped":
                            tqdm.write(f"[{tn:02d}] Skipped")
                        else:
                            tqdm.write(f"[{tn:02d}] Done")
                    pbar.update(1)
            except KeyboardInterrupt:
                tqdm.write("Interrupted by user, cancelling pending tasks...")
                # Signal workers to stop cooperatively
                stop_event.set()
                for f in futures:
                    f.cancel()
                ex.shutdown(wait=False)
                return

    if failures:
        print("\nSome tracks failed to process:")
        for tn, err in failures:
            print(f" - Track {tn}: {err.splitlines()[0]}")

        # Save failed tracks to a log file for reference
        import json
        import time
        failed_tracks_log = []
        for tn, err in failures:
            failed_tracks_log.append({
                'track_number': tn,
                'error': str(err),
                'timestamp': time.time(),
                'playlist_size': len(tracks)
            })

        with open('failed_tracks.json', 'w', encoding='utf-8') as f:
            json.dump(failed_tracks_log, f, indent=2, ensure_ascii=False)

        print(f"\nFailed tracks logged to failed_tracks.json")
    else:
        print("\nAll tracks processed successfully.")

    # Tagging was performed inline after each track completed, so any tagging errors
    # will appear in the 'failures' list above. We already removed per-track cover
    # files after successful tagging to keep the workspace clean.

    if failures:
        print("\nSome tracks failed to process/tag:")
        for tn, err in failures:
            print(f" - Track {tn}: {err.splitlines()[0]}")
    else:
        print("\nAll tracks processed and tagged successfully.")

        # Remove metadata file now that everything succeeded
        try:
            if os.path.exists("metadata_raw.json"):
                os.remove("metadata_raw.json")
                tqdm.write("Removed metadata_raw.json")
        except Exception as e:
            tqdm.write(f"Failed to remove metadata_raw.json: {e}")

        # Move downloaded files into a folder named after the playlist (all tested audio extensions)
        try:
            dest_name = sanitize_filename(playlist_name) or "playlist"
            dest_dir = os.path.join("output", dest_name)
            os.makedirs(dest_dir, exist_ok=True)
            moved = 0
            for fname in os.listdir("output/playlist"):
                if fname.lower().endswith((".mp3", ".m4a", ".mp4", ".ogg", ".aac")):
                    src = os.path.join("output/playlist", fname)
                    dst = os.path.join(dest_dir, fname)
                    try:
                        import shutil

                        shutil.move(src, dst)
                        moved += 1
                    except Exception as e:
                        tqdm.write(f"Failed to move {src} to {dst}: {e}")
            tqdm.write(f"Moved {moved} tracks to {dest_dir}")
        except Exception as e:
            tqdm.write(f"Failed to move tracks to playlist folder: {e}")


if __name__ == "__main__":
    main()
