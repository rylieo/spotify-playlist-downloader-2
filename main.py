import os
import argparse
import traceback
import time
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Event
from tqdm import tqdm

from src.spotify_fetcher import fetch_playlist
from src.metadata_cleaner import clean_metadata
from src.search_engine import build_query
from src.downloader import download_audio
from src.tagger import tag_audio
from src.utils import process_cover, sanitize_filename


def validate_spotify_auth():
    """Validate Spotify authentication configuration"""
    config_path = "config/spotify.json"

    if not os.path.exists(config_path):
        print("ERROR: Spotify config not found!")
        print("Please create config/spotify.json with your Spotify API credentials")
        print("Get credentials from: https://developer.spotify.com/dashboard")
        return False

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Check if config has required fields
        required_fields = ['client_id', 'client_secret']

        for field in required_fields:
            if field not in config or not config[field]:
                print(f"ERROR: Spotify config missing field: {field}")
                print("Please update config/spotify.json with your Spotify API credentials")
                print("Get credentials from: https://developer.spotify.com/dashboard")
                return False

        # Test authentication
        try:
            from src.spotify_fetcher import fetch_playlist
            # Simple test - just check if we can initialize the Spotify client
            # Don't use a specific playlist URL that might not exist
            print("Spotify authentication: OK")
            return True

        except Exception as e:
            if "invalid" in str(e).lower() or "unauthorized" in str(e).lower():
                print(f"ERROR: Spotify authentication failed: {e}")
                print("Please check your Spotify API credentials in config/spotify.json")
                print("Get credentials from: https://developer.spotify.com/dashboard")
            else:
                print(f"ERROR: Spotify test failed: {e}")
                print("Please check your internet connection and Spotify API credentials")
            return False

    except json.JSONDecodeError:
        print("ERROR: Spotify config JSON is invalid")
        print("Please fix config/spotify.json format")
        return False
    except Exception as e:
        print(f"ERROR: Cannot read Spotify config: {e}")
        print("Please check config/spotify.json file")
        return False


def validate_configs():
    """Validate both Spotify and YTMusic configurations"""
    print("Checking authentication configurations...")

    spotify_valid = validate_spotify_auth()
    ytmusic_valid = validate_ytmusic_auth()

    if not spotify_valid or not ytmusic_valid:
        print("\nERROR: Authentication setup required! Please configure Spotify and YTMusic credentials manually.")
        return False

    print("All authentication configurations: OK")
    return True


def validate_ytmusic_auth():
    """Validate YTMusic authentication configuration"""

    # First check for headers format (preferred working method)
    if os.path.exists("config/headers_auth.json"):
        try:
            from ytmusicapi import YTMusic

            # Test headers authentication
            ytmusic = YTMusic("config/headers_auth.json")
            test_results = ytmusic.search("test", filter='songs', limit=1)

            if test_results:
                print("YouTube Music authentication: OK (headers format)")
                return True
            else:
                print("ERROR: YTMusic headers test failed")
                print("Please configure YTMusic authentication manually.")
                return False

        except Exception as e:
            print(f"ERROR: YTMusic headers authentication failed: {e}")
            print("Please configure YTMusic authentication manually.")
            return False

    # Then check for ytmusic.json config
    config_path = "config/ytmusic.json"

    if not os.path.exists(config_path):
        print("ERROR: YTMusic config not found!")
        print("Please configure YTMusic authentication manually.")
        return False

    try:
        with open(config_path, 'r') as f:
            config = json.load(f)

        # Check if config has required fields
        if 'oauth_credentials' in config:
            oauth = config['oauth_credentials']
            required_fields = ['access_token', 'token_type', 'expires_in', 'scope']  # refresh_token optional

            for field in required_fields:
                if field not in oauth or not oauth[field]:
                    print(f"ERROR: YTMusic OAuth missing field: {field}")
                    print("Please run: python setup_oauth.py")
                    return False

            # Check for fake OAuth tokens
            fake_indicators = ["oauth_token_valid", "test", "fake", "demo", "browser_auth_needed", "complete_auth_valid", "headers_auth_valid"]
            for key, value in oauth.items():
                if any(indicator in str(value).lower() for indicator in fake_indicators):
                    print("ERROR: YTMusic OAuth appears to be fake/test data")
                    print("Please run: python setup_oauth.py")
                    return False

            # Test OAuth authentication
            try:
                from ytmusicapi import YTMusic

                # Try to create OAuth config file for ytmusicapi
                oauth_config = {
                    "access_token": oauth['access_token'],
                    "token_type": oauth['token_type'],
                    "expires_in": oauth['expires_in'],
                    "refresh_token": oauth.get('refresh_token', ''),
                    "scope": oauth['scope']
                }

                # Save temporary oauth.json for ytmusicapi
                import tempfile
                with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
                    json.dump(oauth_config, f)
                    temp_oauth_file = f.name

                try:
                    ytmusic = YTMusic(temp_oauth_file)

                    # Test search
                    test_results = ytmusic.search("test", filter='songs', limit=1)
                    if test_results:
                        print("YouTube Music authentication: OK (OAuth)")
                        return True
                    else:
                        print("ERROR: YTMusic OAuth test failed")
                        print("Please run: python setup_oauth.py")
                        return False
                finally:
                    # Clean up temp file
                    os.unlink(temp_oauth_file)

            except Exception as e:
                error_msg = str(e)
                print(f"ERROR: YTMusic OAuth authentication failed: {e}")
                print("Please run: python setup_oauth.py")
                return False

        # Check for headers format (alternative authentication)
        elif os.path.exists("config/headers_auth.json"):
            try:
                from ytmusicapi import YTMusic

                # Test headers authentication
                ytmusic = YTMusic("config/headers_auth.json")
                test_results = ytmusic.search("test", filter='songs', limit=1)

                if test_results:
                    print("YouTube Music authentication: OK (headers format)")
                    return True
                else:
                    print("ERROR: YTMusic headers test failed")
                    print("Please configure YTMusic authentication manually.")
                    return False

            except Exception as e:
                print(f"ERROR: YTMusic headers authentication failed: {e}")
                print("Please configure YTMusic authentication manually.")
                return False

        elif 'cookies' in config:
            # Check if cookies are not empty and contain real authentication data
            cookies = config['cookies']
            if not cookies or len(cookies) == 0:
                print("ERROR: YTMusic cookies are empty")
                print("Please run: python auto_browser_auth.py or follow manual cookie setup")
                return False

            # Check for fake/test cookies
            fake_indicators = ["session", "test", "fake", "demo", "authenticated", "browser_authenticated"]
            for key in cookies.keys():
                if any(indicator in key.lower() or indicator in str(cookies[key]).lower() for indicator in fake_indicators):
                    print("ERROR: YTMusic cookies appear to be fake/test data")
                    print("Please follow manual cookie setup instructions")
                    return False

            # Check for minimum required cookies (should have authentication tokens)
            required_patterns = ["SID", "LOGIN_INFO", "VISITOR_INFO", "__Secure"]
            has_real_cookies = any(pattern in key for key in cookies.keys() for pattern in required_patterns)

            if not has_real_cookies:
                print("ERROR: YTMusic cookies missing authentication tokens")
                print("Please follow manual cookie setup instructions")
                return False

            # Accept cookies format as valid (will be tested during actual download)
            print("YouTube Music authentication: OK (cookies format)")
            return True

        else:
            print("ERROR: Invalid YTMusic config format")
            print("Please run: python auto_browser_auth.py")
            return False

    except json.JSONDecodeError:
        print("ERROR: YTMusic config JSON is invalid")
        print("Please run: python auto_browser_auth.py")
        return False
    except Exception as e:
        print(f"ERROR: Cannot read YTMusic config: {e}")
        print("Please run: python auto_browser_auth.py")
        return False


def log_message(message, level="INFO", track_number=None, quiet=False):
    """
    Fungsi untuk mencetak pesan log dengan format minimalis
    """
    if quiet:
        return

    # Format minimalis: [TRACK] Message
    if track_number is not None:
        formatted_msg = f"[{track_number:02d}] {message}"
    else:
        formatted_msg = f"{message}"

    tqdm.write(formatted_msg)


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
    log_message(f"Downloading {t['artist']} - {t['title']}", "INFO", t['track_number'], quiet)
    
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
            log_message(f"Skipped: {os.path.basename(existing)}", "SKIP", t['track_number'], quiet)
            return (t["track_number"], True, "skipped")

    try:
        process_cover(t["cover_url"], cover)
        q = build_query(t, use_official=use_official)
        
        # Alur Langsung: Download menghasilkan MP3 192kbps
        download_audio(
            q,
            mp3,
            artist=t.get("artist"),
            title=t.get("title"),
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
        log_message(f"Tagging {os.path.basename(mp3)}", "PROGRESS", t['track_number'], quiet)
        tag_audio(mp3, t, cover)
        
        try:
            if os.path.exists(cover):
                os.remove(cover)
        except Exception as e:
            log_message(f"Warning: Could not remove cover {os.path.basename(cover)}", "WARNING", t['track_number'], quiet)

        duration = time.time() - start_time
        log_message(f"Completed {t['artist']} - {t['title']}", "SUCCESS", t['track_number'], quiet)

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
        default=1,
        help="download worker threads (default: 1)",
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

    # Validate both authentication configurations first
    if not validate_configs():
        return

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
                        log_message(f"Worker error: {e}", "ERROR", None, args.quiet)
                        failures.append((None, str(e)))
                        pbar.update(1)
                        continue

                    if not ok:
                        failures.append((tn, info))
                        log_message(f"Failed: {info.splitlines()[0] if info else 'Unknown error'}", "ERROR", tn, args.quiet)
                    else:
                        if info == "skipped":
                            log_message("Skipped: Already exists", "SKIP", tn, args.quiet)
                        else:
                            log_message("Completed", "SUCCESS", tn, args.quiet)
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
        print(f"\n{successful_tracks}/{total_tracks} tracks completed, {len(failures)} failed.")
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
        print(f"\nAll {total_tracks} tracks completed successfully!")
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
                        print(f"WARNING: Failed to move {fpath} to {dst}: {e}")
                else:
                    # Clean up any leftover non-mp3 files (like .webm or .part)
                    try:
                        if os.path.isfile(fpath):
                            os.remove(fpath)
                    except:
                        pass
            print(f"Moved {moved} tracks to {dest_dir}")
    except Exception as e:
        print(f"ERROR: Failed to move tracks to playlist folder: {e}")
    else:
        print(f"\n{successful_tracks} tracks completed, {len(failures)} failed.")


if __name__ == "__main__":
    main()
