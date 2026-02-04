import subprocess
import os
import shutil
import time
import random


def download_audio(
    query,
    output_mp3,
    artist=None,
    duration_ms=None,
    verbose=False,
    search_count=5,
    stop_event=None,
):
    """Download audio for query into output_mp3 using yt-dlp executable.

    Arguments:
        query: search query string
        output_mp3: target mp3 path
        artist: expected artist name for verification (optional)
        duration_ms: target duration from Spotify in milliseconds (optional)
        verbose: if True, show external tool output instead of capturing it
        search_count: number of ytsearch results to consider
        stop_event: optional threading.Event for cancellation
    """
    outdir = os.path.dirname(output_mp3)
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    # Detect a JavaScript runtime (deno/node) for yt-dlp
    js_runtime = None
    for name in ("deno", "node"):
        path = shutil.which(name)
        if path:
            js_runtime = (name, path)
            break

    # Find yt-dlp command
    yt_dlp_path = shutil.which("yt-dlp")
    
    # Fallback search in Python Scripts folder if not in PATH
    if yt_dlp_path is None:
        import sys
        # Check standard Scripts folder relative to python
        scripts_dir = os.path.join(os.path.dirname(sys.executable), "Scripts")
        candidate = os.path.join(scripts_dir, "yt-dlp.exe")
        if os.path.exists(candidate):
            yt_dlp_path = candidate
        else:
            # Check user roaming Scripts folder (common on Windows)
            user_scripts = os.path.join(os.environ.get("APPDATA", ""), "Python", f"Python{sys.version_info.major}{sys.version_info.minor}", "Scripts")
            candidate = os.path.join(user_scripts, "yt-dlp.exe")
            if os.path.exists(candidate):
                yt_dlp_path = candidate

    # Base command: if still not found as exe, use python -m yt_dlp (as a process)
    if yt_dlp_path:
        cmd = [yt_dlp_path]
    else:
        # Final fallback: use the python module as an executable (subprocess)
        # This honors "use only executable" as it runs a separate process CLI
        cmd = [sys.executable, "-m", "yt_dlp"]

    if js_runtime:
        cmd += ["--js-runtimes", f"{js_runtime[0]}:{js_runtime[1]}"]

    # Priority: YT Music (via direct URL search to avoid 'unsupported scheme' errors on some systems)
    # followed by regular YouTube search
    prefixes = ["https://music.youtube.com/search?q=", "ytsearch"]
    
    # query is "Title Artist" from build_query
    query_variants = [query]
    
    # Generate variations
    clean_q = query.lower().replace("official audio", "").strip()
    
    if artist:
        # 1. "Artist - Title" (Standard)
        # 2. "Title - Artist" (Reversed)
        # 3. "Title" only (Aggressive fallback)
        clean_artist = artist.lower()
        title_only = clean_q.replace(clean_artist, "").replace("-", " ").strip()
        
        # Ensure we don't add empty or identical variants
        variants = [
            f"{artist} - {title_only}",
            f"{title_only} - {artist}",
            title_only,
            f"{title_only} {artist}"
        ]
        
        for v in variants:
            if v and len(v) > 2 and v not in query_variants:
                query_variants.append(v)
    else:
        # Just try with/without official audio
        if "official audio" in query.lower():
            query_variants.append(clean_q)
        else:
            query_variants.append(f"{query} official audio")

    last_stderr = ""

    target_s = duration_ms / 1000.0 if duration_ms else None

    unique_candidates = {}
    
    for search_prefix in prefixes:
        for q_var in query_variants:
            # Construct search command
            if search_prefix.startswith("http"):
                # URL-based search (YT Music workaround)
                import urllib.parse
                encoded_q = urllib.parse.quote(q_var)
                search_query = f"{search_prefix}{encoded_q}"
            else:
                # Regular prefix search
                search_query = f"{search_prefix}:{q_var}"

            search_cmd = cmd + [
                "--dump-json", 
                "--flat-playlist", 
                "--playlist-items", f"1-{search_count}",
                search_query
            ]
            
            try:
                proc = subprocess.run(search_cmd, capture_output=True, check=False, timeout=45)
                
                if proc.returncode != 0:
                    last_stderr = proc.stderr.decode("utf-8", errors="replace")
                    continue

                # Parse candidates from JSON lines
                import json
                for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
                    if not line.strip().startswith("{"): continue
                    try:
                        data = json.loads(line)
                        if "id" in data:
                            unique_candidates[data["id"]] = data
                    except:
                        continue
            except Exception as e:
                last_stderr = str(e)
                continue

        # (Strict Phase Separation removed to allow global comparison)

    if not unique_candidates:
        return False

    # Scoring candidates
    scored = []
    candidates = list(unique_candidates.values())
    
    for entry in candidates:
        dur = entry.get("duration")
        if dur is None:
            dur_score = 100
        elif target_s is None:
            dur_score = 0
        else:
            dur_score = abs(dur - target_s)

        title = (entry.get("title") or "").lower()
        uploader = (entry.get("uploader") or "").lower()
        channel = (entry.get("channel") or "").lower()
        is_verified = entry.get("channel_is_verified") or False

        # Penalize non-matching indicators
        # Added "live", "concert" etc to avoid live versions
        indicators = ["remix", "live", "acoustic", "instrumental", "cover", "karaoke", "sped up", "slowed", "concert", "perform", "tour", "video", "official video", "mv"]
        penalty = 0
        for ind in indicators:
            if ind in title and ind not in query.lower():
                penalty += 100 

        # Title Match
        title_penalty = 0
        if artist:
            clean_artist = artist.lower()
            base_clean_title = query.lower().replace("official audio", "").replace(clean_artist, "").strip()
            q_words = [w for w in base_clean_title.split() if len(w) > 2]
            if not q_words: q_words = [w for w in base_clean_title.split() if w]
            
            found_words = sum(1 for w in q_words if w in title)
            if q_words and found_words == 0:
                title_penalty = 180 
            else:
                title_penalty = (len(q_words) - found_words) * 35

        # Artist/Uploader Check
        artist_score = 45 
        if artist:
            a_lower = artist.lower()
            
            # TOPIC SUPREMACY: If it is a Topic channel, it is the highest quality audio (Source of Truth)
            if f"{a_lower} - topic" in uploader or "topic" in uploader or "release - topic" in uploader:
                artist_score = -80 # Massive Bonus for Topic (Beats everything)
            elif a_lower == uploader or a_lower == channel:
                 # Official Artist Channel is good, but videos might have intros
                artist_score = -30
            elif a_lower in uploader or a_lower in channel or uploader in a_lower:
                artist_score = -20
            elif is_verified:
                artist_score = -20
            
            if artist_score > 0 and len(uploader) > 3 and uploader in title:
                artist_score += 70

        # Near-perfect duration bonus
        perfect_dur_bonus = 0
        if target_s and dur:
            diff = abs(dur - target_s)
            if diff < 4.0:
                perfect_dur_bonus = -60 
            elif diff < 8.0:
                perfect_dur_bonus = -25

        # Total score
        total_score = penalty + artist_score + title_penalty + perfect_dur_bonus + (dur_score * 10.0) # Increased duration weight
        scored.append((total_score, entry))

    scored.sort(key=lambda x: x[0])
    
    # Try top candidates until success
    for total_score, entry in scored:
        if stop_event is not None and stop_event.is_set():
            raise KeyboardInterrupt("Cancelled by user")

        dur = entry.get("duration")
        if target_s and dur:
            diff = abs(dur - target_s)
            
            # STRICT DURATION MATCHING requested by user ("100% same")
            # We allow a tiny margin (3s) for platform differences (silence padding)
            # Anything beyond that is likely a different version (video intro, extended mix, etc.)
            tolerance = 3.0
            
            # If we are desperate (score is bad), we might relax slightly, but barely
            if total_score > 50: 
                tolerance = 5.0
                
            if diff > tolerance:
                if verbose:
                    print(f"Skipping {entry.get('title')} - Duration diff {diff:.1f}s > {tolerance:.1f}s")
                continue

        video_url = entry.get("url") or entry.get("webpage_url") or entry.get("id")
        if not video_url: continue

        if verbose:
            print(f"Chosen candidate (Score: {total_score:.1f}): {entry.get('title')} | Uploader: {entry.get('uploader')}")

        download_cmd = cmd + [
            "--no-playlist",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "mp3", "--audio-quality", "192k",
            "-o", output_mp3,
            video_url
        ]
        
        max_attempts = 2
        for attempt in range(1, max_attempts + 1):
            try:
                p_dl = subprocess.Popen(download_cmd, stdout=subprocess.PIPE if not verbose else None, stderr=subprocess.PIPE if not verbose else None)
                ret = p_dl.wait(timeout=180)
                
                # Cleanup intermediate junk
                base_p = os.path.splitext(output_mp3)[0]
                for ext in [".m4a", ".webm", ".f140", ".f251", ".part"]:
                    if os.path.exists(base_p + ext):
                        try: os.remove(base_p + ext)
                        except: pass

                if ret == 0 and os.path.exists(output_mp3) and os.path.getsize(output_mp3) > 1024:
                    return # Success
            except:
                continue
                continue

    raise RuntimeError(f"Download failed for {query}. Last error: {last_stderr}")
