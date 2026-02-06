import subprocess
import os
import shutil
import time
import random

from .smart_resolver import smart_resolve_track


def download_audio(
    query,
    output_mp3,
    artist=None,
    duration_ms=None,
    isrc=None,
    album=None,
    title=None,
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
        isrc: ISRC code from Spotify (optional, for 100% match)
        album: Album name from Spotify (optional, for scoring)
        title: Track title from Spotify (optional, for ytmusic search)
        verbose: if True, show external tool output instead of capturing it
        search_count: number of ytsearch results to consider
        stop_event: optional threading.Event for cancellation
    """
    outdir = os.path.dirname(output_mp3)
    if outdir:
        os.makedirs(outdir, exist_ok=True)

    # Check for cookies file (SAFE METHOD for age-restricted content)
    cookies_file = "config/cookies.txt"
    
    if os.path.exists(cookies_file):
        if verbose:
            print(f"Using cookies from {cookies_file} for age-restricted content")
        cookies_arg = ["--cookies", cookies_file]
    else:
        # Try OAuth2 authentication as fallback
        if verbose:
            print("No cookies found, trying OAuth2 authentication...")
        cookies_arg = ["--username", "oauth2", "--password", ""]
        oauth2_active = True
    
    # ... (JS runtime and yt-dlp path detection code remains same)
    js_runtime = None
    for name in ("deno", "node"):
        path = shutil.which(name)
        if path:
            js_runtime = (name, path)
            break

    yt_dlp_path = shutil.which("yt-dlp")
    if yt_dlp_path is None:
        import sys
        # Try Python module method
        try:
            import yt_dlp
            # Check if yt_dlp module is available
            cmd = [sys.executable, "-m", "yt_dlp"]
        except ImportError:
            print("ERROR: yt-dlp not found! Please install: pip install yt-dlp")
            return False
    else:
        cmd = [yt_dlp_path]

    if js_runtime:
        cmd += ["--js-runtimes", f"{js_runtime[0]}:{js_runtime[1]}"]
    
    # Add cookies argument
    cmd += cookies_arg
    
    # Add JavaScript challenge solver with Node.js (DISABLED - causes issues)
    # cmd += ["--remote-components", "ejs:github"]
    
    # Force audio format selection to avoid downloading only images
    cmd += ["--extract-audio", "--audio-format", "mp3", "--audio-quality", "192k"]
    
    # Add fallback option without JavaScript challenge
    cmd += ["--no-check-certificate"]
    
    # Force Node.js runtime
    if js_runtime:
        cmd += ["--js-runtimes", f"{js_runtime[0]}:{js_runtime[1]}"]
    else:
        # Try to find Node.js
        node_path = shutil.which("node")
        if node_path:
            cmd += ["--js-runtimes", f"node:{node_path}"]
        else:
            # Fallback to system Node.js
            cmd += ["--js-runtimes", "node"]

    prefixes = ["https://music.youtube.com/search?q=", "ytsearch"]
    query_variants = [query]
    
    clean_q = query.lower().replace("official audio", "").strip() if query else ""
    
    if artist:
        clean_artist = artist.lower() if artist else ""
        title_only = clean_q.replace(clean_artist, "").replace("-", " ").strip()
        variants = [
            f"{artist} - {title_only}",
            f"{title_only} - {artist}",
            title_only,
            f"{title_only} {artist}"
        ]
        for v in variants:
            if v and len(v) > 2 and v not in query_variants:
                query_variants.append(v)
    
    # ENABLE SMART RESOLVER FOR ACCURACY
    from src.smart_resolver import SmartResolver
    resolver = SmartResolver()
    
    # Create target_track dict from parameters
    target_track = {
        'artist': artist,
        'title': title,
        'duration_ms': duration_ms,
        'isrc': isrc,
        'album': album
    }
    
    ytmusic_result = resolver.resolve_track(target_track, verbose=verbose)
    
    last_stderr = ""
    target_s = duration_ms / 1000.0 if duration_ms else None
    unique_candidates = {}
    
    # Add Smart Resolver result (highest priority - ISRC-First)
    if ytmusic_result:
        video_id = ytmusic_result.get('video_id')
        if video_id:
            # Convert smart resolver result to yt-dlp format
            candidate = {
                'id': video_id,
                'title': ytmusic_result.get('title', ''),
                'uploader': ', '.join(ytmusic_result.get('artists', [])),
                'duration': ytmusic_result.get('duration', 0),
                'isrc': ytmusic_result.get('isrc', ''),
                'album': ytmusic_result.get('album', ''),
                'url': ytmusic_result.get('url', ''),
                'confidence': ytmusic_result.get('confidence', 0),
                'from_smart_resolver': True,
                'resolved': True
            }
            unique_candidates[video_id] = candidate
            if verbose:
                confidence = ytmusic_result.get('confidence', 0)
                print(f"Added SMART RESOLVED track: {ytmusic_result.get('title')} (confidence: {confidence:.2f})")
    
    # Traditional yt-dlp search as fallback
    for search_prefix in prefixes:
        for q_var in query_variants:
            if search_prefix.startswith("http"):
                import urllib.parse
                encoded_q = urllib.parse.quote(q_var)
                search_query = f"{search_prefix}{encoded_q}"
            else:
                search_query = f"{search_prefix}:{q_var}"

            search_cmd = cmd + [
                "--dump-json", 
                "--flat-playlist", 
                "--playlist-items", f"1-{search_count}",
                search_query
            ] + cookies_arg
            
            try:
                proc = subprocess.run(search_cmd, capture_output=True, check=False, timeout=45)
                if proc.returncode != 0:
                    last_stderr = proc.stderr.decode("utf-8", errors="replace")
                    continue

                import json
                for line in proc.stdout.decode("utf-8", errors="replace").splitlines():
                    if not line.strip().startswith("{"): continue
                    try:
                        data = json.loads(line)
                        if "id" in data:
                            # Don't overwrite smart resolver results
                            if data["id"] not in unique_candidates or not unique_candidates[data["id"]].get("from_smart_resolver"):
                                # Check for ISRC match early if available
                                cand_isrc = data.get("isrc")
                                if isrc and cand_isrc and (isrc.lower() if isrc else "") == (cand_isrc.lower() if cand_isrc else ""):
                                    data["isrc_match"] = True
                                    if verbose: print(f"DEBUG: ISRC MATCH found in search results for {data['id']}")
                                unique_candidates[data["id"]] = data
                    except:
                        continue
            except Exception as e:
                last_stderr = str(e)
                continue

    if not unique_candidates:
        return False

    def get_score(cand_entry):
        # SMART RESOLVER MATCH - ABSOLUTE HIGHEST PRIORITY (ISRC-First)
        if cand_entry.get("from_smart_resolver") and cand_entry.get("resolved"):
            confidence = cand_entry.get("confidence", 0)
            if verbose: print(f"SMART RESOLVER MATCH - Highest priority for {cand_entry.get('title')} (confidence: {confidence:.2f})")
            return -9999999, 0  # Absolute highest priority
        
        # ISRC MATCH - HIGH PRIORITY
        if cand_entry.get("isrc_match"):
            if verbose: print(f"DEBUG: ISRC MATCH - High priority for {cand_entry.get('title')}")

        dur = cand_entry.get("duration")
        if dur is None:
            dur_score = 100
        elif target_s is None:
            dur_score = 0
        else:
            dur_score = abs(dur - target_s)

        title = (cand_entry.get("title") or "").lower()
        uploader = (cand_entry.get("uploader") or "").lower()
        channel = (cand_entry.get("channel") or "").lower()
        is_verified = cand_entry.get("channel_is_verified") or False
        cand_album = (cand_entry.get("album") or "").lower()

        indicators = ["remix", "live", "acoustic", "instrumental", "cover", "karaoke", "sped up", "slowed", "concert", "perform", "tour", "video", "official video", "mv"]
        penalty = 0
        for ind in indicators:
            if ind in title and ind not in (query.lower() if query else ""):
                is_official_source = artist and (artist.lower() if artist else "" in uploader or (artist.lower() if artist else "" in channel))
                if (ind in ["video", "official video", "mv"]) and (is_official_source or is_verified):
                    penalty += 40 
                else:
                    penalty += 100 

        title_penalty = 0
        if artist:
            import re
            def get_words(s):
                s = s.lower().replace("official audio", "").replace("official music video", "")
                return set(re.findall(r'\w+', s))

            # clean_artist is defined in the outer scope, but for clarity and self-containment
            # within the function, we can re-derive it or pass it. Let's re-derive.
            local_clean_artist = artist.lower() if artist else ""
            q_title_part = (query.lower() if query else "").replace(local_clean_artist, "").strip()
            q_words = get_words(q_title_part)
            t_words = get_words(title)

            if q_words:
                found_words = sum(1 for w in q_words if w in t_words)
                match_ratio = found_words / len(q_words)
                if found_words == 0:
                    title_penalty = 250
                elif match_ratio < 0.5:
                    title_penalty = (len(q_words) - found_words) * 75
                else:
                    title_penalty = (len(q_words) - found_words) * 35

        artist_score = 45 
        if artist:
            a_lower = artist.lower() if artist else ""
            if f"{a_lower} - topic" in uploader or "topic" in uploader or "release - topic" in uploader:
                artist_score = -150 
            elif a_lower == uploader or a_lower == channel:
                artist_score = -30
            elif a_lower in uploader or a_lower in channel or uploader in a_lower:
                artist_score = -20
            elif is_verified:
                artist_score = -20
            
            if artist_score > 0 and len(uploader) > 3 and uploader in title:
                artist_score += 70

        album_bonus = 0
        if album and cand_album:
            if (album.lower() if album else "" in cand_album or cand_album in (album.lower() if album else "")):
                album_bonus = -50

        # PRIORITIZE SMART RESOLVER RESULTS (ISRC-First)
        smart_resolver_bonus = 0
        if entry.get("from_smart_resolver"):
            smart_resolver_bonus = -1000  # Highest priority
        elif entry.get("isrc_match"):
            smart_resolver_bonus = -500   # High priority for ISRC matches

        perfect_dur_bonus = 0
        if target_s and dur:
            diff = abs(dur - target_s)
            if diff < 2.0:
                perfect_dur_bonus = -80 
            elif diff < 5.0:
                perfect_dur_bonus = -30

        total_score = penalty + artist_score + title_penalty + perfect_dur_bonus + album_bonus + smart_resolver_bonus + (dur_score * 15.0)
        return total_score, title_penalty

    scored = []
    for entry in unique_candidates.values():
        score, _ = get_score(entry)
        scored.append((score, entry))

    scored.sort(key=lambda x: x[0])
    
    # Try top candidates until success
    for initial_score, entry in scored:
        if stop_event is not None and stop_event.is_set():
            raise KeyboardInterrupt("Cancelled by user")

        video_id = entry.get("id")
        if not video_id: continue
        
        # FORCE EARLY RETURN for high confidence smart resolver results
        if entry.get("from_smart_resolver") and entry.get("resolved"):
            confidence = entry.get("confidence", 0)
            if confidence >= 0.9:  # High confidence threshold
                if verbose: 
                    print(f"USING HIGH CONFIDENCE SMART RESOLVER: {entry.get('title')} (confidence: {confidence:.2f})")
                    print(f"   Video ID: {video_id}")
                    print(f"   Duration: {entry.get('duration', 0)}s")
                
                # Skip all other candidates and use this one directly
                video_id = entry.get("id")
                
                # If crucial info is missing or it looks like a false title match, fetch full metadata
                title = entry.get("title") or ""
                dur = entry.get("duration")
                uploader = entry.get("uploader")
                
                needs_fetch = not title or dur is None or uploader is None
                
                if needs_fetch:
                    try:
                        if verbose: print(f"DEBUG: Fetching full metadata for {video_id}...")
                        full_cmd = cmd + ["-J", video_id] + cookies_arg
                        proc_full = subprocess.run(full_cmd, capture_output=True, text=True, timeout=20)
                        if proc_full.returncode == 0:
                            full_data = json.loads(proc_full.stdout)
                            # Update entry with full metadata
                            entry.update(full_data)
                            title = entry.get("title") or ""
                            dur = entry.get("duration")
                            uploader = entry.get("uploader")
                    except Exception as e:
                        if verbose: print(f"DEBUG: Full metadata fetch failed: {e}")
                
                # Proceed with download using this high confidence result
                try:
                    # Build download command
                    download_cmd = cmd + [
                        "-f", "bestaudio/best",
                        "-x", "--audio-format", "mp3", "--audio-quality", "192k",
                        "-o", output_mp3,
                        f"https://music.youtube.com/watch?v={video_id}"
                    ]
                    
                    if verbose:
                        print(f"Downloading: {title} ({video_id})")
                    
                    proc = subprocess.run(download_cmd, capture_output=True, check=False, timeout=180)
                    
                    if proc.returncode == 0:
                        if verbose: print(f"Download successful: {output_mp3}")
                        return True
                    else:
                        if verbose: print(f"Download failed: {proc.stderr.decode('utf-8', errors='replace')}")
                        continue  # Try next candidate
                        
                except Exception as e:
                    if verbose: print(f"Download error: {e}")
                    continue  # Try next candidate
        
        # Original logic for other candidates (non-high-confidence smart resolver)
        # If crucial info is missing or it looks like a false title match, fetch full metadata
        title = entry.get("title") or ""
        dur = entry.get("duration")
        uploader = entry.get("uploader")
        
        needs_fetch = not title or dur is None or uploader is None
        
        if needs_fetch:
            try:
                if verbose: print(f"DEBUG: Fetching full metadata for {video_id}...")
                full_cmd = cmd + ["-J", video_id] + cookies_arg
                proc_full = subprocess.run(full_cmd, capture_output=True, text=True, timeout=20)
                if proc_full.returncode == 0:
                    full_data = json.loads(proc_full.stdout)
                    entry.update(full_data) # Update with ALL new metadata
                    # Re-check ISRC after full fetch
                    cand_isrc = full_data.get("isrc")
                    if isrc and cand_isrc and (isrc.lower() if isrc else "") == (cand_isrc.lower() if cand_isrc else ""):
                        entry["isrc_match"] = True
                        if verbose: print(f"DEBUG: ISRC MATCH confirmed after full fetch for {video_id}!")
            except:
                pass

        # RE-CALCULATE EVERYTHING based on final metadata
        total_score, title_penalty = get_score(entry)
        dur = entry.get("duration")
        uploader = (entry.get("uploader") or "").lower()

        # Additional validation for YTMusic results
        if entry.get("from_ytmusic") and entry.get("is_song"):
            # YTMusic results are pre-validated, but still check duration
            if target_s:
                dur = entry.get("duration")
                if dur:
                    duration_diff = abs(dur - target_s)
                    # Even for YTMusic, reject if duration is very different
                    if duration_diff > 15.0:  # More than 15 seconds different
                        if verbose: print(f"Skipping YTMusic result {entry.get('title')} - Duration diff too high: {duration_diff:.1f}s")
                        continue
        else:
            # Traditional search results need very strict validation
            if target_s:
                if dur:
                    diff = abs(dur - target_s)
                    
                    # VERY STRICT: Reject if duration is more than 15 seconds different
                    if diff > 15.0:
                        if verbose: print(f"Skipping {entry.get('title')} - Duration diff {diff:.1f}s > 15.0s limit")
                        continue

        video_url = entry.get("url") or entry.get("webpage_url") or video_id
        if not video_url: continue

        if verbose:
            print(f"Chosen candidate (Score: {total_score:.1f}): {entry.get('title')} | Uploader: {uploader}")

        download_cmd = cmd + [
            "--no-playlist",
            "-f", "bestaudio/best",
            "-x", "--audio-format", "mp3", "--audio-quality", "192k",
        ] + cookies_arg + [
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

    raise RuntimeError(f"Download failed for {query}. Last error: {last_stderr}")
