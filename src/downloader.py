import subprocess
import os
import shutil
import time
import random


def download_audio(
    query,
    output_wav,
    duration_ms=None,
    no_fallback=False,
    verbose=False,
    search_count=5,
    use_official=True,
    source="youtube",
    stop_event=None,
):
    """Download audio for query into output_wav.

    Arguments:
        query: search query string
        output_wav: target wav path
        duration_ms: target duration from Spotify in milliseconds (optional)
        no_fallback: if True, do not attempt Python `yt_dlp` API fallback
        verbose: if True, show external tool output instead of capturing it
        search_count: number of ytsearch results to consider when choosing candidate
        use_official: boolean; kept for compatibility (query already includes official terms)
        stop_event: optional threading.Event that, when set, requests cancellation
    """
    """Download audio for query into output_wav.

    Arguments:
        query: search query string
        output_wav: target wav path
        duration_ms: target duration from Spotify in milliseconds (optional)
        no_fallback: if True, do not attempt Python `yt_dlp` API fallback
        verbose: if True, show external tool output instead of capturing it
        search_count: number of ytsearch results to consider when choosing candidate
        use_official: boolean; kept for compatibility (query already includes official terms)
    """
    outdir = os.path.dirname(output_wav)
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    # Detect a JavaScript runtime (deno/node)
    js_runtime = None
    for name in ("deno", "node"):
        path = shutil.which(name)
        if path:
            js_runtime = (name, path)
            break

    # Helper: attempt using yt-dlp executable (subprocess)
    def _run_with_exe():
        yt_dlp_path = shutil.which("yt-dlp")
        if yt_dlp_path is None:
            return False, "yt-dlp executable not found"

        cmd = [yt_dlp_path]
        if js_runtime:
            cmd += ["--js-runtimes", f"{js_runtime[0]}:{js_runtime[1]}"]

        # Try search prefixes in order with YouTube Music as primary source
        prefixes = ["ytmusicsearch1:", "ytsearch1:"]
        cmd += [
            "--no-playlist",
            "-f",
            "bestaudio/best",
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "0",
            "-o",
            output_wav.replace('.wav', '.mp3'),
            f"{prefixes[0]}{query}",
        ]

        # store prefixes for potential retry attempts
        cmd_search_prefixes = prefixes

        # Attempt initial prefix first, then fallback to the alternate prefix if available
        tried = []
        for prefix_attempt, search_prefix in enumerate(cmd_search_prefixes):
            tried.append(search_prefix)
            cmd[-1] = f"{search_prefix}{query}"
            max_attempts = 3
            delay = 1
            for attempt in range(1, max_attempts + 1):
                # Respect cooperative cancellation between attempts
                if stop_event is not None and stop_event.is_set():
                    return False, "cancelled by user"

                try:
                    capture_flag = not verbose
                    stdout_pipe = subprocess.PIPE if capture_flag else None
                    stderr_pipe = subprocess.PIPE if capture_flag else None
                    candidate_timeout = 180  # seconds per candidate attempt
                    start_time = time.time()
                    proc = subprocess.Popen(cmd, stdout=stdout_pipe, stderr=stderr_pipe)

                    # Wait with periodic checks to allow cancellation and enforce timeout
                    while True:
                        try:
                            ret = proc.wait(timeout=1)
                            break
                        except subprocess.TimeoutExpired:
                            # Check for cooperative cancellation
                            if stop_event is not None and stop_event.is_set():
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                                proc.wait()
                                return False, "cancelled by user"

                            # Enforce candidate-level timeout to avoid infinite hangs
                            if time.time() - start_time > candidate_timeout:
                                try:
                                    proc.kill()
                                except Exception:
                                    pass
                                try:
                                    proc.wait(timeout=5)
                                except Exception:
                                    pass
                                ret = -1
                                stderr = f"yt-dlp executable timed out after {candidate_timeout}s"
                                break
                            continue

                    # capture stderr if we need it
                    stderr = ""
                    if ret != 0:
                        # if stderr already set by timeout, keep it
                        if not stderr and stderr_pipe and proc.stderr:
                            try:
                                stderr = proc.stderr.read().decode(
                                    "utf-8", errors="replace"
                                )
                            except Exception:
                                stderr = f"yt-dlp failed with return code {ret}"
                        elif not stderr:
                            stderr = f"yt-dlp failed with return code {ret}"

                    # Verify that a valid MP3 file was produced by yt-dlp
                    candidate_paths = [output_wav.replace('.wav', '.mp3')]
                    if not output_wav.lower().endswith(".wav"):
                        candidate_paths.append(output_wav + ".mp3")

                    found_good = False
                    for p in candidate_paths:
                        try:
                            if os.path.exists(p) and os.path.getsize(p) > 1024:
                                # If yt-dlp wrote a file with .mp3 extension, move it to the expected path
                                if p != output_wav:
                                    try:
                                        shutil.move(p, output_wav)
                                    except Exception:
                                        pass
                                found_good = True
                                break
                        except OSError:
                            # ignore file access errors and treat as missing
                            pass

                    if found_good:
                        return True, ""

                    # yt-dlp reported success but produced no valid wav; clean any partials and continue attempts
                    if verbose:
                        print(
                            f"yt-dlp run completed but no valid WAV found at {candidate_paths}"
                        )
                    for p in candidate_paths:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

                    # if there was an error, allow immediate prefix fallback for unavailable video
                    if "This video is not available" in (
                        stderr or ""
                    ) or "ERROR: unable to obtain file audio codec" in (stderr or ""):
                        if verbose:
                            print(
                                f"Prefix {search_prefix} failed: {(stderr or '').splitlines()[0]}"
                            )
                        break

                    stderr = stderr or "yt-dlp produced no valid wav file"
                    # continue to next attempt for this prefix
                    if attempt < max_attempts:
                        sleep_for = delay + random.uniform(0, delay)
                        time.sleep(sleep_for)
                        delay *= 2
                        continue
                    # exhausted attempts for this prefix, move to next prefix
                    break

                except Exception as e:
                    stderr = str(e)
                    # Remove any partial files left by yt-dlp for this attempt
                    candidate_paths = [output_wav]
                    if not output_wav.lower().endswith(".wav"):
                        candidate_paths.append(output_wav + ".wav")
                    for p in candidate_paths:
                        try:
                            if os.path.exists(p):
                                os.remove(p)
                        except Exception:
                            pass

                    if "No supported JavaScript runtime" in stderr or "EJS" in stderr:
                        return False, stderr

                    if (
                        "This video is not available" in stderr
                        or "ERROR: unable to obtain file audio codec" in stderr
                    ):
                        if verbose:
                            print(
                                f"Prefix {search_prefix} failed: {stderr.splitlines()[0]}"
                            )
                        break

                    if attempt < max_attempts:
                        sleep_for = delay + random.uniform(0, delay)
                        time.sleep(sleep_for)
                        delay *= 2
                        continue
                    # exhausted attempts for this prefix, move to next prefix
                    break
        # if we get here, all prefixes/attempts failed
        return False, f"tried prefixes: {tried}; last error: {stderr}"

    # Ensure ffprobe (part of ffmpeg) is available for postprocessing
    ffprobe_path = shutil.which("ffprobe")

    # First try executable if available
    ok, msg = _run_with_exe()
    if ok:
        return

    if no_fallback:
        raise RuntimeError(f"yt-dlp executable failed: {msg}")

    # If exe failed or not present, try Python yt_dlp API as a fallback
    try:
        import importlib.util

        spec = importlib.util.find_spec("yt_dlp")
    except Exception:
        spec = None

    if spec is None:
        # No module fallback available; provide helpful message
        hints = []
        if "No supported JavaScript runtime" in msg or "EJS" in (msg or ""):
            hints.append(
                "yt-dlp needs a JavaScript runtime (deno or node). Install one (e.g. `winget install denoland.deno` or `winget install OpenJS.NodeJS.LTS`) or ensure it's in PATH."
            )
        if "ffprobe" in (msg or "") and not ffprobe_path:
            hints.append(
                "ffprobe not found. Install ffmpeg (which includes ffprobe) and add it to your PATH."
            )
        raise RuntimeError(
            f"yt-dlp executable failed and Python module 'yt_dlp' not available. Last error: {msg}\nHints: {' | '.join(hints)}"
        )

    # Use yt_dlp Python API
    try:
        import yt_dlp

        # prepare outtmpl so the postprocessor writes .wav as desired
        if output_wav.lower().endswith(".wav"):
            outtmpl = output_wav[:-4] + ".%(ext)s"
        else:
            outtmpl = output_wav + ".%(ext)s"

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl.replace('.wav', '.mp3'),
            "noplaylist": True,
            "quiet": not verbose,
            "no_warnings": not verbose,
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ],
        }

        # Use yt_dlp Python API to search multiple candidates and choose the best by duration/title
        try:
            last_exc = None
            with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True}) as ydl:
                # Always try YouTube Music as primary source, then YouTube as fallback
                prefixes = ["ytmusicsearch", "ytsearch"]
                entries = []
                last_search_err = None
                for p in prefixes:
                    try:
                        search_query = f"{p}{search_count}:{query}"
                        if verbose:
                            print(f"Searching with prefix {p}: {search_query}")
                        info = ydl.extract_info(search_query, download=False)
                        entries = info.get("entries") or []
                        if entries:
                            break
                    except Exception as e:
                        last_search_err = e
                        if verbose:
                            print(f"Search with prefix {p} failed: {e}")
                        continue

            if not entries:
                raise RuntimeError(
                    f"No search results from yt_dlp API (tried prefixes {prefixes}): {last_search_err}"
                )

            target_s = duration_ms / 1000.0 if duration_ms else None

            # Extract artist from query for comparison
            # Assuming query format is "title artist official audio" or similar
            query_parts = query.lower().split()
            artist_from_query = ""
            if len(query_parts) > 2:
                # Take the last few words as potential artist name
                artist_words = query_parts[-3:]  # Last 3 words as potential artist
                artist_from_query = " ".join(artist_words)

            def score_entry(entry, idx):
                dur = entry.get("duration")
                if dur is None:
                    dur_score = float("inf")
                elif target_s is None:
                    dur_score = 0
                else:
                    dur_score = abs(dur - target_s)

                title = (entry.get("title") or "").lower()
                uploader = (entry.get("uploader") or "").lower()

                # prefer titles that contain the track title words
                title_match = 0
                if query:
                    q = query.split(" ")
                    # count how many query words appear in title
                    title_match = -sum(
                        1 for w in q if len(w) > 2 and w.lower() in title
                    )

                # additional scoring based on uploader/artist match
                uploader_match = 0
                if artist_from_query and len(artist_from_query) > 2:
                    # penalize if uploader doesn't contain artist name
                    if artist_from_query not in uploader:
                        uploader_match = 1  # small penalty

                # check if title contains common non-matching indicators
                non_matching_indicators = ["remix", "live", "acoustic", "instrumental", "cover", "version"]
                indicator_penalty = 0
                for indicator in non_matching_indicators:
                    if indicator in title and indicator not in query.lower():
                        indicator_penalty += 2  # penalty for potential mismatch

                return (dur_score, uploader_match, title_match, indicator_penalty, idx)

            # Score all entries and sort
            scored = [(score_entry(e, i), e) for i, e in enumerate(entries)]
            scored.sort()

            if not scored:
                raise RuntimeError("No search results from yt_dlp API")

            # Try candidates in score order until one downloads successfully
            download_errors = []
            for rank, (s, entry) in enumerate(scored, start=1):
                # Respect cooperative cancellation between candidates
                if stop_event is not None and stop_event.is_set():
                    return

                out_url = entry.get("webpage_url") or entry.get("url")
                if not out_url:
                    download_errors.append((entry.get("id"), "no url"))
                    continue

                # Check duration match before attempting download
                if target_s and entry.get("duration"):
                    tol = max(5, int(target_s * 0.08))  # tolerance is max of 5 seconds or 8% of track duration (tighter tolerance)
                    duration_diff = abs(entry.get("duration") - target_s)
                    if duration_diff > tol:
                        if verbose:
                            print(
                                f"Candidate {rank} duration differs by {duration_diff:.1f}s (>{tol:.1f}s tolerance): {entry.get('duration')} vs {target_s}s, skipping"
                            )
                        continue  # Skip this candidate if duration mismatch is too large
                    elif verbose:
                        print(
                            f"Candidate {rank} duration match: {entry.get('duration')}s vs {target_s}s (tolerance: {tol:.1f}s)"
                        )

                if verbose:
                    print(
                        f"Trying candidate {rank}/{len(scored)}: {entry.get('title')} ({out_url})"
                    )

                # attempt download for this candidate
                max_attempts = 2
                delay = 1
                for attempt in range(1, max_attempts + 1):
                    if stop_event is not None and stop_event.is_set():
                        return

                    try:
                        expected_mp3 = outtmpl.replace("%(ext)s", "mp3").replace('.wav', '.mp3')
                        # remove any stale/partial expected mp3 before attempting
                        try:
                            if os.path.exists(expected_mp3):
                                os.remove(expected_mp3)
                        except Exception:
                            pass

                        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                            # run download and periodically check for cancellation
                            done = False

                            def _run_and_monitor():
                                try:
                                    ydl.download([out_url])
                                finally:
                                    nonlocal done
                                    done = True

                            import threading

                            th = threading.Thread(target=_run_and_monitor, daemon=True)
                            th.start()

                            # wait for the thread but poll for stop_event and enforce timeout
                            candidate_timeout = 180  # seconds per candidate
                            start_time = time.time()
                            while th.is_alive():
                                th.join(timeout=1)
                                if stop_event is not None and stop_event.is_set():
                                    # we can't forcibly stop ydl.download, but we can return early
                                    # allow the background thread to finish/cleanup on its own
                                    download_errors.append(
                                        (entry.get("id"), "cancelled")
                                    )
                                    return
                                if time.time() - start_time > candidate_timeout:
                                    if verbose:
                                        print(
                                            f"Candidate {rank} timed out after {candidate_timeout}s"
                                        )
                                    download_errors.append((entry.get("id"), "timeout"))
                                    # stop waiting and move to next candidate
                                    break

                        # check that expected mp3 file exists and is not empty
                        if (
                            os.path.exists(expected_mp3)
                            and os.path.getsize(expected_mp3) > 1024
                        ):
                            # Move the downloaded MP3 to the expected WAV path to maintain consistency
                            shutil.move(expected_mp3, output_wav)
                            return

                        # else treat as failure and try next candidate
                        download_errors.append(
                            (entry.get("id"), "no valid wav produced")
                        )
                        break

                    except Exception as e:
                        download_errors.append((entry.get("id"), str(e)))
                        if attempt < max_attempts:
                            sleep_for = delay + random.uniform(0, delay)
                            time.sleep(sleep_for)
                            delay *= 2
                            continue
                        # move to next candidate
                        break

            # If we reach here, none of the candidates worked
            raise RuntimeError(f"All candidate downloads failed: {download_errors}")
        except Exception as e:
            # if Python API fails, we'll fall back to the executable flow below (unless no_fallback)
            last_exc = e
            if no_fallback:
                raise RuntimeError(f"yt_dlp API search/download failed: {e}") from e
            # otherwise, continue to try executable-based download

    except Exception as e:
        raise RuntimeError(
            f"Failed to download using yt-dlp (exe) and yt_dlp API fallback. Last error: {msg if not spec else str(e)}"
        ) from e
