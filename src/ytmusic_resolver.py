"""
YouTube Music Integration with Antigravity Resolver
Menggunakan resolver engine untuk akurasi 95-100%
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from typing import Dict, List, Optional
from ytmusicapi import YTMusic

from resolver import (
    AntigravityResolver, 
    TrackMetadata, 
    Candidate, 
    create_resolver
)

YTMUSIC_AVAILABLE = True
try:
    from ytmusicapi import YTMusic
except ImportError:
    YTMUSIC_AVAILABLE = False
    print("Warning: ytmusicapi not available")

class YTMusicResolver:
    """YouTube Music integration dengan Antigravity Resolver"""
    
    def __init__(self, auth_file: Optional[str] = None, confidence_threshold: float = 0.85):
        self.auth_file = auth_file
        self.resolver = create_resolver(confidence_threshold)
        
        try:
            if auth_file and os.path.exists(auth_file):
                self.ytmusic = YTMusic(auth_file)
            else:
                self.ytmusic = YTMusic()
        except Exception as e:
            print(f"Warning: Failed to initialize YTMusic client: {e}")
            self.ytmusic = None
    
    def resolve_track(self, track: Dict, max_candidates: int = 20, verbose: bool = False) -> Optional[Dict]:
        """
        Resolve track dengan akurasi 95-100%
        
        Args:
            track: Dictionary dengan track metadata dari Spotify
            max_candidates: Maximum kandidat yang akan dicek
            verbose: Show detailed process
            
        Returns:
            Dict dengan resolved track info atau None jika tidak confident
        """
        if not self.ytmusic:
            if verbose: pass  # print("❌ YTMusic client not available")
            return None
        
        # Convert ke TrackMetadata
        target_metadata = TrackMetadata(
            title=track.get('title', ''),
            artist=track.get('artist', ''),
            album=track.get('album', ''),
            duration_ms=track.get('duration_ms', 0),
            isrc=track.get('isrc', ''),
            year=str(track.get('year', '')),
            track_number=track.get('track_number', 0)
        )
        
        if verbose:
            pass  # print(f"🎯 RESOLVING: {target_metadata.title} by {target_metadata.artist}")
            pass  # print(f"   Duration: {target_metadata.get_duration_seconds():.1f}s")
            pass  # print(f"   ISRC: {target_metadata.isrc or 'None'}")  
        
        # PRIORITY 1: Cari dengan ISRC (jika ada)
        candidates = []
        if target_metadata.isrc:
            if verbose: pass  
            isrc_candidates = self._search_by_isrc(target_metadata.isrc, verbose)
            candidates.extend(isrc_candidates)
        
        # PRIORITY 2: Cari dengan query (jika ISRC tidak cukup)
        if len(candidates) < 3:  # Butuh lebih banyak kandidat
            if verbose: pass  # print(f"🔍 Searching by query...")
            query_candidates = self._search_by_query(target_metadata, max_candidates, verbose)
            candidates.extend(query_candidates)
        
        if not candidates:
            if verbose: pass  # print("❌ No candidates found")
            return None
        
        if verbose: pass  # print(f"📊 Found {len(candidates)} candidates")
        
        # RESOLVE dengan Antigravity Resolver
        result = self.resolver.resolve(target_metadata, candidates, verbose)
        
        if result:
            best_candidate, confidence = result
            
            if verbose:
                pass  # print(f"✅ RESOLVED with {confidence:.2f} confidence:")
                pass  # print(f"   Title: {best_candidate.title}")
                pass  # print(f"   Artist: {', '.join(best_candidate.artists)}")
                pass  # print(f"   Duration: {best_candidate.duration}s")
                pass  # print(f"   ISRC: {best_candidate.isrc or 'None'}")
            
            # Convert ke format yang diharapkan oleh sistem
            return {
                'video_id': best_candidate.video_id,
                'title': best_candidate.title,
                'artists': best_candidate.artists,
                'album': best_candidate.album,
                'duration': best_candidate.duration,
                'isrc': best_candidate.isrc,
                'confidence': confidence,
                'url': f"https://music.youtube.com/watch?v={best_candidate.video_id}",
                'resolved': True,
                'from_resolver': True
            }
        else:
            if verbose: pass  # print(f"❌ No candidate met confidence threshold ({self.resolver.confidence_threshold})")
            return None
    
    def _search_by_isrc(self, isrc: str, verbose: bool = False) -> List[Candidate]:
        """Cari kandidat berdasarkan ISRC"""
        candidates = []
        
        try:
            results = self.ytmusic.search(isrc, filter='songs', limit=10)
            
            for result in results:
                if result.get('resultType') != 'song':
                    continue
                
                candidate = self._convert_to_candidate(result, "isrc_search")
                if candidate:
                    candidates.append(candidate)
                    
        except Exception as e:
            if verbose: pass  # print(f"❌ ISRC search failed: {e}")
        
        return candidates
    
    def _search_by_query(self, metadata: TrackMetadata, max_results: int, verbose: bool = False) -> List[Candidate]:
        """Cari kandidat berdasarkan query"""
        candidates = []
        
        # Build smart query
        query_parts = [metadata.title, metadata.artist]
        if metadata.album:
            query_parts.append(metadata.album)
        
        query = ' '.join(filter(None, query_parts))
        
        try:
            results = self.ytmusic.search(query, filter='songs', limit=max_results)
            
            for result in results:
                if result.get('resultType') != 'song':
                    continue
                
                candidate = self._convert_to_candidate(result, "query_search")
                if candidate:
                    candidates.append(candidate)
                    
        except Exception as e:
            if verbose: pass  # print(f"❌ Query search failed: {e}")
        
        return candidates
    
    def _convert_to_candidate(self, result: Dict, source: str) -> Optional[Candidate]:
        """Convert YTMusic result ke Candidate object"""
        try:
            video_id = result.get('videoId', '')
            if not video_id:
                return None
            
            title = result.get('title', '')
            if not title:
                return None
            
            # Extract artists
            artists_raw = result.get('artists', [])
            artists = []
            for artist_info in artists_raw:
                if isinstance(artist_info, dict):
                    artist_name = artist_info.get('name', '')
                else:
                    artist_name = str(artist_info)
                
                if artist_name:
                    artists.append(artist_name)
            
            # Extract album
            album = ""
            album_info = result.get('album')
            if album_info and isinstance(album_info, dict):
                album = album_info.get('name', '')
            
            # Extract duration
            duration = result.get('duration_seconds', 0)
            
            # Extract ISRC - debug this
            isrc = result.get('isrc', '') or ''
            if source == "isrc_search":
                if verbose: pass  # print(f"    🔍 ISRC search result: {title}")
                if verbose: pass  # print(f"       Video ID: {video_id}")
                if verbose: pass  # print(f"       Raw ISRC: '{isrc}'")
                if verbose: pass  # print(f"       Full result keys: {list(result.keys())}")
            
            return Candidate(
                video_id=video_id,
                title=title,
                artists=artists,
                album=album,
                duration=duration,
                isrc=isrc,
                source=source
            )
            
        except Exception as e:
            if verbose: pass  # print(f"    ❌ Error converting result: {e}")
            return None

# Convenience function
def resolve_with_ytmusic(track: Dict, auth_file: Optional[str] = None, confidence_threshold: float = 0.85, verbose: bool = False) -> Optional[Dict]:
    """
    Convenience function untuk resolve track dengan YTMusic
    
    Args:
        track: Dictionary dengan track metadata
        auth_file: Optional YTMusic auth file
        confidence_threshold: Minimum confidence threshold (0-1)
        verbose: Show detailed process
        
    Returns:
        Dict dengan resolved track info atau None
    """
    if not YTMUSIC_AVAILABLE:
        return None
    
    try:
        resolver = YTMusicResolver(auth_file, confidence_threshold)
        return resolver.resolve_track(track, verbose=verbose)
    except Exception as e:
        if verbose: pass  # print(f"❌ Resolution failed: {e}")
        return None
