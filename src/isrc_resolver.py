"""
Antigravity ISRC-First Resolver Engine
Berdasarkan analisis yang benar: ISRC tidak searchable langsung di YT Music
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass

from ytmusic_resolver import YTMusicResolver, TrackMetadata, Candidate

@dataclass
class ISRCMetadata:
    """Metadata dari ISRC lookup (Spotify/MusicBrainz)"""
    title: str
    artist: str
    album: str
    duration_ms: int
    year: str
    isrc: str
    is_explicit: bool = False

class AntigravityISRCResolver:
    """ISRC-First Resolver Engine - 95-100% akurat"""
    
    def __init__(self, spotify_client_id: str, spotify_client_secret: str):
        self.spotify = spotipy.Spotify(
            client_credentials_manager=SpotifyClientCredentials(
                client_id=spotify_client_id,
                client_secret=spotify_client_secret
            )
        )
        self.ytmusic_resolver = YTMusicResolver(confidence_threshold=0.75)  # Turunkan ke 0.75
    
    def resolve_by_isrc(self, isrc: str, verbose: bool = False) -> Optional[Dict]:
        """
        Resolve track by ISRC dengan pipeline yang benar
        
        Args:
            isrc: ISRC code
            verbose: Debug output
            
        Returns:
            Resolved track dict atau None
        """
        if verbose:
            print(f"RESOLVING ISRC: {isrc}")
        
        # STEP 1: Get metadata dari ISRC (Spotify)
        isrc_metadata = self._get_isrc_metadata(isrc, verbose)
        if not isrc_metadata:
            if verbose:
                    print(f"ISRC {isrc} tidak ditemukan di Spotify")
            return None
        
        if verbose:
            print(f"ISRC Metadata found:")
            print(f"   Title: {isrc_metadata.title}")
            print(f"   Artist: {isrc_metadata.artist}")
            print(f"   Album: {isrc_metadata.album}")
            print(f"   Duration: {isrc_metadata.duration_ms}ms ({isrc_metadata.duration_ms/1000:.1f}s)")
        
        # STEP 2: Convert ke TrackMetadata
        track_metadata = TrackMetadata(
            title=isrc_metadata.title,
            artist=isrc_metadata.artist,
            album=isrc_metadata.album,
            duration_ms=isrc_metadata.duration_ms,
            isrc=isrc_metadata.isrc,
            year=isrc_metadata.year
        )
        
        # STEP 3: Resolve dengan YTMusic (bukan search!)
        result = self.ytmusic_resolver.resolve_track(track_metadata.__dict__, verbose=verbose)
        
        if result:
            confidence = result.get('confidence', 0)
            result_title = result.get('title', '')
            result_artists = result.get('artists', [])
            
            # STEP 4: ISRC Collision Detection
            if verbose:
                print(f"Checking for ISRC collision...")
                print(f"   Expected: {isrc_metadata.title} by {isrc_metadata.artist}")
                print(f"   Got: {result_title} by {', '.join(result_artists)}")
            
            # Check if result matches expected metadata
            title_match = self._calculate_title_similarity(isrc_metadata.title, result_title)
            artist_match = self._calculate_artist_similarity(isrc_metadata.artist, result_artists)
            
            if verbose:
                print(f"   Title similarity: {title_match:.2f}")
                print(f"   Artist similarity: {artist_match:.2f}")
            
            # If title or artist don't match well, it's likely ISRC collision
            # Relaxed threshold for sped up/instrumental versions
            if title_match < 0.5 or artist_match < 0.7:
                if verbose:
                    print(f"ISRC COLLISION DETECTED! Falling back to metadata-based resolver...")
                
                # Fallback to metadata-based resolver without ISRC
                fallback_track = {
                    'title': isrc_metadata.title,
                    'artist': isrc_metadata.artist,
                    'album': isrc_metadata.album,
                    'duration_ms': isrc_metadata.duration_ms,
                    'isrc': None,  # Remove ISRC to avoid collision
                    'year': isrc_metadata.year
                }
                
                fallback_result = self.ytmusic_resolver.resolve_track(fallback_track, verbose=verbose)
                if fallback_result:
                    fallback_confidence = fallback_result.get('confidence', 0)
                    if verbose:
                        print(f"FALLBACK RESOLVED with {fallback_confidence:.2f} confidence")
                    return fallback_result
                else:
                    if verbose:
                        print(f"Fallback resolution also failed")
                    return None
            else:
                if verbose:
                    print(f"ISRC match verified - no collision")
                
                # STEP 5: Validate Video ID Accessibility
                video_id = result.get('video_id')
                if video_id and verbose:
                    print(f"Validating video ID accessibility: {video_id}")
                
                # Validate that the video ID is actually accessible
                if video_id and self._validate_video_id(video_id, verbose=verbose):
                    if verbose:
                        print(f"Video ID is accessible")
                        print(f"ISRC RESOLVED with {confidence:.2f} confidence")
                        print(f"   Title: {result.get('title')}")
                        print(f"   Artists: {', '.join(result.get('artists', []))}")
                        print(f"   Duration: {result.get('duration')}s")
                        print(f"   URL: {result.get('url')}")
                    
                    return result
                else:
                    if verbose:
                        print(f"ERROR: Video ID is not accessible, falling back to metadata search...")
                    
                    # Fallback to metadata-based resolver without ISRC
                    fallback_track = {
                        'title': isrc_metadata.title,
                        'artist': isrc_metadata.artist,
                        'album': isrc_metadata.album,
                        'duration_ms': isrc_metadata.duration_ms,
                        'isrc': None,  # Remove ISRC to avoid collision
                        'year': isrc_metadata.year
                    }
                    
                    fallback_result = self.ytmusic_resolver.resolve_track(fallback_track, verbose=verbose)
                    if fallback_result:
                        fallback_confidence = fallback_result.get('confidence', 0)
                        if verbose:
                            print(f"FALLBACK RESOLVED with {fallback_confidence:.2f} confidence")
                        return fallback_result
                    else:
                        if verbose:
                            print(f"Fallback resolution also failed")
                        return None
        else:
            if verbose:
                print(f"ISRC {isrc} tidak bisa di-resolve dengan confidence >= 0.75")
            return None
    
    def _validate_video_id(self, video_id: str, verbose: bool = False) -> bool:
        """Validate that a video ID is accessible via YTMusic API"""
        try:
            if verbose:
                print(f"   INFO: Testing video ID: {video_id}")

            # Try to get watch playlist for this video ID
            watch_playlist = self.ytmusic_resolver.ytmusic.get_watch_playlist(video_id)

            if not watch_playlist:
                if verbose:
                    print(f"   ERROR: Watch playlist not accessible")
                return False

            # Check if tracks exist
            tracks = watch_playlist.get('tracks', [])
            if not tracks:
                if verbose:
                    print(f"   ERROR: No tracks in watch playlist")
                return False
            
            # Get the first track
            track = tracks[0]
            title = track.get('title', '')
            artists = [artist.get('name', '') for artist in track.get('artists', [])]
            
            # Check for age restriction indicators
            watch_playlist_headers = watch_playlist.get('headers', {})
            if watch_playlist_headers:
                # Check for age restriction in headers
                if any('age' in str(header).lower() or 'restricted' in str(header).lower()
                       for header in watch_playlist_headers.values()):
                    if verbose:
                        print(f"   ERROR: Age-restricted video detected")
                    return False
            
            # Check if video is age-restricted by trying to access it directly
            try:
                # Try to search for the video ID directly
                search_results = self.ytmusic_resolver.ytmusic.search(video_id, limit=1)
                if not search_results:
                    if verbose:
                        print(f"   ERROR: Video ID not found in search (possibly restricted)")
                    return False
            except Exception as e:
                if verbose:
                    print(f"   ERROR: Error searching for video ID: {e}")
                return False
            
            if verbose:
                print(f"   SUCCESS: Video accessible: {title} by {', '.join(artists)}")

            return True

        except Exception as e:
            if verbose:
                print(f"   ERROR: Error validating video ID: {e}")
            return False
    
    def _calculate_title_similarity(self, expected_title: str, actual_title: str) -> float:
        """Calculate title similarity for collision detection"""
        if not expected_title or not actual_title:
            return 0.0
        
        expected_lower = expected_title.lower()
        actual_lower = actual_title.lower()
        
        # Exact match
        if expected_lower == actual_lower:
            return 1.0
        
        # Clean common suffixes/prefixes for version comparison
        def clean_title(title):
            # Remove common version indicators
            suffixes = [
                ' - sped up', ' (sped up)', ' sped up',
                ' - instrumental', ' (instrumental)', ' instrumental',
                ' - clean', ' (clean)', ' clean',
                ' - explicit', ' (explicit)', ' explicit',
                ' - radio edit', ' (radio edit)', ' radio edit',
                ' - remix', ' (remix)', ' remix',
                ' - version', ' (version)', ' version'
            ]
            cleaned = title
            for suffix in suffixes:
                if cleaned.endswith(suffix):
                    cleaned = cleaned[:-len(suffix)]
                    break
            return cleaned.strip()
        
        expected_clean = clean_title(expected_lower)
        actual_clean = clean_title(actual_lower)
        
        # Check if clean titles match (for sped up, instrumental, etc.)
        if expected_clean == actual_clean and expected_clean != actual_lower:
            return 0.9  # High similarity for version variants
        
        # Check if expected title is contained in actual title
        if expected_lower in actual_lower or actual_lower in expected_lower:
            return 0.8
        
        # Check if clean titles are contained
        if expected_clean in actual_clean or actual_clean in expected_clean:
            return 0.7
        
        # Word-based similarity
        expected_words = set(expected_clean.split())
        actual_words = set(actual_clean.split())
        
        if expected_words and actual_words:
            intersection = expected_words & actual_words
            union = expected_words | actual_words
            if union:
                return len(intersection) / len(union)
        
        return 0.0
    
    def _calculate_artist_similarity(self, expected_artist: str, actual_artists: List[str]) -> float:
        """Calculate artist similarity for collision detection"""
        if not expected_artist or not actual_artists:
            return 0.0
        
        expected_lower = expected_artist.lower()
        
        for artist in actual_artists:
            if not artist:
                continue
            actual_lower = artist.lower()
            
            # Exact match
            if expected_lower == actual_lower:
                return 1.0
            
            # Contains match
            if expected_lower in actual_lower or actual_lower in expected_lower:
                return 0.8
        
        return 0.0
    
    def _get_isrc_metadata(self, isrc: str, verbose: bool = False) -> Optional[ISRCMetadata]:
        """Get metadata dari ISRC menggunakan Spotify API"""
        try:
            # Search by ISRC di Spotify
            results = self.spotify.search(q=f"isrc:{isrc}", type="track", limit=1)
            
            if not results['tracks']['items']:
                return None
            
            track = results['tracks']['items'][0]
            
            return ISRCMetadata(
                title=track['name'],
                artist=track['artists'][0]['name'],
                album=track['album']['name'],
                duration_ms=track['duration_ms'],
                year=str(track['album']['release_date'][:4]),
                isrc=track.get('external_ids', {}).get('isrc', isrc),
                is_explicit=track['explicit']
            )
            
        except Exception as e:
            if verbose:
                print(f"Error getting ISRC metadata: {e}")
            return None

# Factory function
def create_isrc_resolver(spotify_client_id: str, spotify_client_secret: str) -> AntigravityISRCResolver:
    """Create ISRC resolver instance"""
    return AntigravityISRCResolver(spotify_client_id, spotify_client_secret)

# Convenience function
def resolve_track_by_isrc(isrc: str, verbose: bool = False) -> Optional[Dict]:
    """
    Convenience function untuk resolve track by ISRC
    
    Args:
        isrc: ISRC code
        verbose: Debug output
        
    Returns:
        Resolved track dict atau None
    """
    try:
        # Load Spotify credentials
        import json
        with open('config/spotify.json', 'r') as f:
            spotify_config = json.load(f)
        
        resolver = create_isrc_resolver(
            spotify_config['client_id'], 
            spotify_config['client_secret']
        )
        
        return resolver.resolve_by_isrc(isrc, verbose)
        
    except Exception as e:
        if verbose:
            print(f"ISRC resolution failed: {e}")
        return None
