import os
import json
import time
from typing import Dict, List, Optional, Tuple

try:
    from ytmusicapi import YTMusic
    YTMUSIC_AVAILABLE = True
except ImportError:
    YTMUSIC_AVAILABLE = False
    print("WARNING: ytmusicapi not installed. Run 'pip install ytmusicapi' to enable YouTube Music search.")

class YTMusicSearcher:
    def __init__(self, auth_file: Optional[str] = None):
        """Initialize YouTube Music searcher.
        
        Args:
            auth_file: Path to YTMusic auth JSON file. If None, uses unauthenticated access.
        """
        if not YTMUSIC_AVAILABLE:
            raise ImportError("ytmusicapi is not installed")
        
        self.auth_file = auth_file
        self.ytmusic = None
        self._init_client()
    
    def _init_client(self):
        """Initialize YTMusic client."""
        try:
            if self.auth_file and os.path.exists(self.auth_file):
                self.ytmusic = YTMusic(self.auth_file)
            else:
                # Use unauthenticated access (still works for search)
                self.ytmusic = YTMusic()
        except Exception as e:
            print(f"WARNING: Failed to initialize YTMusic client: {e}")
            self.ytmusic = None
    
    def search_track(self, track: Dict, max_results: int = 10, verbose: bool = False) -> List[Dict]:
        """Search for a track on YouTube Music.
        
        Args:
            track: Dictionary with title, artist, album, duration_ms, isrc
            max_results: Maximum number of results to return
            
        Returns:
            List of search results with metadata
        """
        if not self.ytmusic:
            return []
        
        # PRIORITY 1: Search by ISRC if available (most accurate)
        isrc = track.get('isrc')
        if isrc and isrc.strip():
            if verbose: print(f"Searching by ISRC: {isrc}")
            try:
                # Search by ISRC - FIXED: Use None filter to get video IDs
                isrc_results = self.ytmusic.search(isrc, filter=None, limit=5)
                if verbose: print(f"Found {len(isrc_results)} results by ISRC")
                
                # Process ISRC results with highest priority
                scored_results = []
                for result in isrc_results:
                    if result.get('resultType') != 'song':
                        continue
                    
                    # Enhanced filtering for ISRC results too
                    title_lower = result.get('title', '').lower()
                    if any(indicator in title_lower for indicator in [
                        'official video', 'music video', 'mv', 'video clip', 
                        'live performance', 'live at', 'concert', 'remix',
                        'instrumental', 'karaoke', 'cover', 'acoustic',
                        'behind the scenes', 'making of', 'interview'
                    ]):
                        if verbose: print(f"SKIP ISRC: Excluding non-song content: {result.get('title')}")
                        continue
                    
                    # Ensure it has artists
                    if not result.get('artists') or len(result.get('artists', [])) == 0:
                        if verbose: print(f"SKIP ISRC: No artists found: {result.get('title')}")
                        continue
                    
                    processed = self._process_search_result(result, track, verbose=verbose)
                    if processed:
                        # ISRC matches get highest priority
                        processed['score'] = -50000  # Extremely high priority
                        processed['isrc_match'] = True
                        scored_results.append(processed)
                
                if scored_results:
                    if verbose: print(f"SUCCESS: Found exact ISRC match(es): {len(scored_results)}")
                    return scored_results
            except Exception as e:
                if verbose: print(f"ISRC search failed: {e}")
        
        # PRIORITY 2: Search by title + artist if ISRC not found
        query_parts = [track.get('title', ''), track.get('artist', '')]
        if track.get('album'):
            query_parts.append(track.get('album', ''))
        
        query = ' '.join(filter(None, query_parts))
        if verbose: print(f"Searching by query: {query}")
        
        try:
            # Search for songs only with strict filtering - FIXED: Use None filter to get video IDs
            search_results = self.ytmusic.search(query, filter=None, limit=max_results)
            
            # Process and score results with additional validation
            scored_results = []
            for result in search_results:
                # Strict validation: ensure it's actually a song
                if result.get('resultType') != 'song':
                    continue
                
                # Additional validation: ensure essential song metadata exists
                if not result.get('videoId') or not result.get('title'):
                    continue
                
                # Ensure it has duration (songs should have duration)
                if not result.get('duration_seconds') and not result.get('duration'):
                    continue
                
                # Enhanced filtering: exclude music videos and non-song content
                title_lower = result.get('title', '').lower()
                if any(indicator in title_lower for indicator in [
                    'official video', 'music video', 'mv', 'video clip', 
                    'live performance', 'live at', 'concert', 'remix',
                    'instrumental', 'karaoke', 'cover', 'acoustic',
                    'behind the scenes', 'making of', 'interview'
                ]):
                    if verbose: print(f"SKIP: Excluding non-song content: {result.get('title')}")
                    continue
                
                # Ensure it has artists (songs should have artists)
                if not result.get('artists') or len(result.get('artists', [])) == 0:
                    if verbose: print(f"SKIP: No artists found: {result.get('title')}")
                    continue
                
                # Ensure it's not an album or playlist result
                if result.get('resultType') in ['album', 'playlist', 'artist', 'video']:
                    continue
                
                processed = self._process_search_result(result, track, verbose=verbose)
                if processed:
                    scored_results.append(processed)
            
            # Sort by score (lower is better)
            scored_results.sort(key=lambda x: x['score'])
            return scored_results
            
        except Exception as e:
            print(f"Error searching YouTube Music: {e}")
            return []
    
    def _process_search_result(self, result: Dict, target_track: Dict, verbose: bool = False) -> Optional[Dict]:
        """Process and score a single search result."""
        try:
            # Extract basic info with proper null checks
            title_raw = result.get('title')
            title = title_raw.lower() if title_raw else ''
            
            artists_raw = result.get('artists', [])
            artists = [artist.get('name', '') for artist in artists_raw if artist and artist.get('name')]
            
            album_raw = result.get('album')
            album = album_raw.get('name', '').lower() if album_raw and album_raw.get('name') else ''
            
            duration = result.get('duration_seconds', 0)
            isrc = result.get('isrc', '') or ''
            video_id = result.get('videoId', '') or ''
            
            # Calculate match score
            score = 0
            
            # ISRC match (highest priority) - already handled in search_track
            # This is just for additional verification
            if result.get('isrc_match'):
                score = -50000  # Highest priority for ISRC matches
                if verbose: print(f"SUCCESS: ISRC MATCH CONFIRMED: {isrc}")
            else:
                # Regular ISRC matching logic for non-ISRC searches
                target_isrc_raw = target_track.get('isrc')
                target_isrc = target_isrc_raw.lower() if target_isrc_raw else ''
                isrc_raw = isrc
                isrc_lower = isrc_raw.lower() if isrc_raw else ''

                if target_isrc and isrc_lower and target_isrc == isrc_lower:
                    score -= 10000  # Perfect match
                    if verbose: print(f"SUCCESS: ISRC MATCH FOUND: {target_isrc}")
            
            # Duration match - EXTREMELY strict validation (max 1 second difference)
            target_duration = target_track.get('duration_ms', 0) / 1000.0
            if target_duration and duration:
                duration_diff = abs(duration - target_duration)
                
                # VERY STRICT: Only allow 1 second difference max
                if duration_diff <= 1.0:
                    score -= 2000  # Huge bonus for exact duration match
                elif duration_diff <= 2.0:
                    score -= 1000  # Good bonus for very close
                elif duration_diff <= 5.0:
                    score -= 500   # Small bonus for close
                elif duration_diff > 10.0:  # More than 10 seconds different
                    score += 2000  # Heavy penalty
                elif duration_diff > 5.0:   # More than 5 seconds different
                    score += 1000  # Moderate penalty
            elif target_duration and not duration:
                score += 1500  # Heavy penalty for missing duration
            
            # Title match
            target_title_raw = target_track.get('title')
            target_title = target_title_raw.lower() if target_title_raw else ''
            title_words = set(target_title.split())
            result_title_words = set(title.split())
            
            if title_words:
                common_words = title_words & result_title_words
                title_match_ratio = len(common_words) / len(title_words)
                if title_match_ratio > 0.8:
                    score -= 300  # Good title match
                elif title_match_ratio > 0.5:
                    score -= 100  # Partial title match
                else:
                    score += 200  # Poor title match
            
            # Artist match
            target_artist_raw = target_track.get('artist')
            target_artist = target_artist_raw.lower() if target_artist_raw else ''
            artist_match = any(target_artist in (artist.lower() if artist else '') for artist in artists)
            if artist_match:
                score -= 200  # Artist match
            else:
                score += 300  # No artist match
            
            # Album match
            target_album_raw = target_track.get('album')
            target_album = target_album_raw.lower() if target_album_raw else ''
            if target_album and album:
                if target_album in album or album in target_album:
                    score -= 100  # Album match
            
            # Penalty for unwanted indicators - more strict
            unwanted_indicators = ['live', 'remix', 'cover', 'acoustic', 'karaoke', 'instrumental', 'remastered', 'version', 'edit']
            for indicator in unwanted_indicators:
                if indicator in title and indicator not in target_title:
                    score += 300  # Increased penalty
            
            # Strict validation for exact matches
            # Title must contain most words from target title
            if title_words:
                common_words = title_words & result_title_words
                match_ratio = len(common_words) / len(title_words)
                
                # Very strict scoring
                if match_ratio < 0.7:  # Must match at least 70% of words
                    score += 500  # Heavy penalty for poor title match
                elif match_ratio < 0.9:  # Less than 90% match
                    score += 200  # Moderate penalty
            
            # Artist must match exactly or very closely
            if target_artist:
                artist_match = any(target_artist in (artist.lower() if artist else '') for artist in artists)
                if not artist_match:
                    score += 400  # Heavy penalty for no artist match
                elif not any(target_artist == (artist.lower() if artist else '') for artist in artists):
                    score += 100  # Penalty for partial artist match
            
            # Final validation - reject clearly wrong matches
            # Must have reasonable title match
            if title_words:
                common_words = title_words & result_title_words
                match_ratio = len(common_words) / len(title_words)
                
                # VERY STRICT for non-ISRC searches: require better title match
                if not result.get('isrc_match'):  # If not an ISRC match
                    if match_ratio < 0.5:  # Require at least 50% title match
                        if verbose: print(f"REJECT: Poor title match '{title}' for target '{target_title_raw}' (ratio: {match_ratio:.2f})")
                        return None
                
                # EXTREMELY STRICT: Reject if duration is very different (more than 30 seconds)
                if target_duration and duration:
                    duration_diff = abs(duration - target_duration)
                    if duration_diff > 30.0:  # More than 30 seconds different
                        if verbose: print(f"REJECT: Duration too different {duration}s vs {target_duration}s (diff: {duration_diff:.1f}s) for '{title}'")
                        return None
                
                # Additional validation for exact title matches - only for very short titles
                if len(target_title.split()) == 1:  # Only single word titles
                    exact_match = target_title_raw.lower().strip() == title.lower().strip()
                    if not exact_match and match_ratio < 0.7:
                        if verbose: print(f"REJECT: Single word title but not close match '{title}' vs '{target_title_raw}'")
                        return None
            
            return {
                'video_id': video_id,
                'title': title_raw or '',
                'artists': artists,
                'album': album_raw.get('name', '') if album_raw else '',
                'duration': duration,
                'isrc': isrc,
                'score': score,
                'url': f"https://music.youtube.com/watch?v={video_id}" if video_id else None
            }
            
        except Exception as e:
            print(f"Error processing search result: {e}")
            return None
    
    def get_best_match(self, track: Dict, max_results: int = 10) -> Optional[Dict]:
        """Get the best matching result for a track."""
        results = self.search_track(track, max_results)
        return results[0] if results else None


def search_with_ytmusic(track: Dict, auth_file: Optional[str] = None, max_results: int = 10, verbose: bool = False) -> List[Dict]:
    """Convenience function to search YouTube Music for a track.
    
    Args:
        track: Dictionary with track metadata
        auth_file: Optional YTMusic auth file path
        max_results: Maximum number of results to return
        
    Returns:
        List of scored search results (songs only)
    """
    if not YTMUSIC_AVAILABLE:
        return []
    
    try:
        searcher = YTMusicSearcher(auth_file)
        results = searcher.search_track(track, max_results, verbose=verbose)
        
        # Log the results for debugging
        if results:
            print(f"YTMusic: Found {len(results)} songs for '{track.get('title', '')}' by '{track.get('artist', '')}'")
        else:
            print(f"YTMusic: No songs found for '{track.get('title', '')}' by '{track.get('artist', '')}'")
        
        return results
    except Exception as e:
        print(f"Error in YouTube Music search: {e}")
        return []
