import os
import argparse
import traceback
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
from tqdm import tqdm

from src.spotify_fetcher import fetch_playlist
from src.metadata_cleaner import clean_metadata
from src.search_engine import build_query
from src.downloader import download_audio
from src.tagger import tag_audio
from src.utils import process_cover, sanitize_filename


def log_message(message, level="INFO", track_number=None, quiet=False):
    """
    Fungsi untuk mencetak pesan log dengan format konsisten
    """
    if quiet:
        return

    prefix = f"[{level}]"
    if track_number is not None:
        prefix = f"[{track_number:02d}] [{level}]"

    tqdm.write(f"{prefix} {message}")


def process_track(
    t,
    quiet=False,
    verbose=False,
    force=False,
    use_official=True,
    search_count=5,
    stop_event=None,
):
    if stop_event is not None and stop_event.is_set():
        raise KeyboardInterrupt()

    start_time = time.time()
    log_message(f"START: {t['artist']} - {t['title']}", "INFO", t['track_number'], quiet)
    
    base = f'{t["track_number"]:02d} - {t["artist"]} - {t["title"]}'
    safe_base = sanitize_filename(base)
    outfilename = f"{safe_base}.mp3"
    mp3 = os.path.join("output", "playlist", outfilename)
    cover = f'assets/covers/{t["track_number"]}.jpg'

    # Check for existing file
    if not force:
        search_key = sanitize_filename(f"{t['artist']} - {t['title']}")
        existing = None
        if os.path.exists("output/playlist"):
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
            log_message(f"SKIPPED (exists): {os.path.basename(existing)}", "SKIP", t['track_number'], quiet)
            return (t["track_number"], True, "skipped")

    try:
        log_message(f"DOWNLOAD: {base}", "PROGRESS", t['track_number'], quiet)
        process_cover(t["cover_url"], cover)
        q = build_query(t, use_official=use_official)
        
        # Alur Langsung: Download menghasilkan MP3 192kbps
        download_audio(
            q,
            mp3,
            artist=t.get("artist"),
            duration_ms=t.get("duration_ms"),
            isrc=t.get("isrc"),
            album=t.get("album"),
            verbose=verbose,
            search_count=search_count,
            stop_event=stop_event,
        )

        # Verify output
        if not (os.path.exists(mp3) and os.path.getsize(mp3) > 1024):
            raise RuntimeError(f"Downloaded audio missing or invalid: {mp3}")

        # Tagging
        log_message(f"TAGGING: {os.path.basename(mp3)}", "PROGRESS", t['track_number'], quiet)
        tag_audio(mp3, t, cover)
        
        try:
            if os.path.exists(cover):
                os.remove(cover)
        except Exception as e:
            log_message(f"Failed to remove cover {os.path.basename(cover)}: {e}", "WARNING", t['track_number'], quiet)

        duration = time.time() - start_time
        log_message(f"COMPLETED ({duration:.1f}s): {t['artist']} - {t['title']}", "SUCCESS", t['track_number'], quiet)

        return (
            t["track_number"],
            True,
            {"mp3": mp3, "meta": t, "cover": cover, "skipped": False},
        )
    except Exception as e:
        try:
            if os.path.exists(mp3):
                os.remove(mp3)
        except:
            pass
        return (t["track_number"], False, str(e) + "\n" + traceback.format_exc())


def main():
    parser = argparse.ArgumentParser(description="Spotify playlist downloader (Direct MP3 192kbps)")
    parser.add_argument("playlist", nargs="?", help="Spotify playlist URL")
    parser.add_argument(
        "-w",
        "--workers",
        type=int,
        default=min(4, (os.cpu_count() or 1) * 2),
        help="download worker threads (default: auto)",
    )
    parser.add_argument("--quiet", action="store_true", help="less verbose output")
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

    args = parser.parse_args()

    playlist_url = args.playlist or input("Spotify playlist URL: ")

    raw = fetch_playlist(playlist_url)
    if isinstance(raw, tuple) or isinstance(raw, list):
        tracks, playlist_name = raw
    else:
        tracks = raw
        playlist_name = "playlist"

    tracks = clean_metadata(tracks)

    os.makedirs("assets/covers", exist_ok=True)
    os.makedirs("output/playlist", exist_ok=True)

    stop_event = Event()
    failures = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = {
            ex.submit(
                process_track,
                t,
                args.quiet,
                args.verbose,
                args.force,
                not args.no_official,
                args.search_count,
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
                        log_message(f"Worker failed: {e}", "ERROR", None, args.quiet)
                        failures.append((None, str(e)))
                        pbar.update(1)
                        continue

                    if not ok:
                        failures.append((tn, info))
                        log_message(f"FAILED: {info.splitlines()[0] if info else 'Unknown error'}", "ERROR", tn, args.quiet)
                    else:
                        if info == "skipped":
                            log_message("SKIPPED: Already exists", "SKIP", tn, args.quiet)
                        else:
                            log_message("SUCCESS: Completed", "SUCCESS", tn, args.quiet)
                    pbar.update(1)
            except KeyboardInterrupt:
                log_message("Interrupted by user, cancelling pending tasks...", "INFO", None, args.quiet)
                stop_event.set()
                for f in futures:
                    f.cancel()
                ex.shutdown(wait=False)
                return

    total_tracks = len(tracks)
    successful_tracks = total_tracks - len(failures)

    if failures:
        print(f"\n[SUMMARY] {successful_tracks}/{total_tracks} tracks processed successfully, {len(failures)} failed.")
        import json
        failed_tracks_log = []
        for tn, err in failures:
            failed_tracks_log.append({
                'track_number': tn,
                'error': str(err),
                'timestamp': time.time()
            })
        with open('failed_tracks.json', 'w', encoding='utf-8') as f:
            json.dump(failed_tracks_log, f, indent=2, ensure_ascii=False)
    else:
        print(f"\n[SUCCESS] All {total_tracks} tracks processed successfully!")
        if os.path.exists("metadata_raw.json"):
            os.remove("metadata_raw.json")

    # Move files to playlist folder
    try:
        dest_name = sanitize_filename(playlist_name) or "playlist"
        dest_dir = os.path.join("output", dest_name)
        os.makedirs(dest_dir, exist_ok=True)
        moved = 0
        if os.path.exists("output/playlist"):
            for fname in os.listdir("output/playlist"):
                fpath = os.path.join("output/playlist", fname)
                if fname.lower().endswith(".mp3"):
                    dst = os.path.join(dest_dir, fname)
                    try:
                        import shutil
                        shutil.move(fpath, dst)
                        moved += 1
                    except Exception as e:
                        print(f"[WARNING] Failed to move {fpath} to {dst}: {e}")
                else:
                    # Clean up any leftover non-mp3 files (like .webm or .part)
                    try:
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                    except:
                        pass
            print(f"[INFO] Moved {moved} tracks to {dest_dir}")
    except Exception as e:
        print(f"[ERROR] Failed to move tracks to playlist folder: {e}")
    else:
        print(f"\n[INFO] Partial success: {successful_tracks} tracks completed, {len(failures)} failed.")


if __name__ == "__main__":
    main()
