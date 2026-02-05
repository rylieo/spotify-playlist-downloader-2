"""
Antigravity Smart Resolver
ISRC-First dengan Smart Fallback untuk operational use
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from .isrc_resolver import AntigravityISRCResolver
from .ytmusic_resolver import resolve_with_ytmusic

class SmartResolver:
    """Smart Resolver: ISRC-First dengan fallback"""
    
    def __init__(self):
        try:
            import json
            with open('config/spotify.json', 'r') as f:
                spotify_config = json.load(f)
            
            self.isrc_resolver = AntigravityISRCResolver(
                spotify_config['client_id'],
                spotify_config['client_secret']
            )
            self.has_spotify = True
        except:
            self.isrc_resolver = None
            self.has_spotify = False
    
    def resolve_track(self, track: Dict, verbose: bool = False) -> Optional[Dict]:
        """
        Smart resolve track dengan ISRC-first approach
        
        Args:
            track: Dictionary dengan track metadata
            verbose: Debug output
            
        Returns:
            Resolved track dict atau None
        """
        isrc = track.get('isrc') or ''
        
        # STEP 1: Try ISRC-First jika ada ISRC dan Spotify available
        if isrc and self.has_spotify:
            if verbose:
                print(f"Trying ISRC-First resolution for {isrc}")
            
            isrc_result = self.isrc_resolver.resolve_by_isrc(isrc, verbose=verbose)
            
            if isrc_result:
                confidence = isrc_result.get('confidence', 0)
                if verbose:
                    print(f"ISRC resolved with {confidence:.2f} confidence")
                return isrc_result
            else:
                if verbose:
                    print(f"ISRC resolution failed, falling back...")
        
        # STEP 2: Fallback ke metadata-based resolver
        if verbose:
            print(f"Using metadata-based resolver...")
        
        metadata_result = resolve_with_ytmusic(
            track, 
            confidence_threshold=0.50,  # Realistis threshold untuk operational
            verbose=verbose
        )
        
        if metadata_result:
            confidence = metadata_result.get('confidence', 0)
            if verbose:
                print(f"Metadata resolved with {confidence:.2f} confidence")
            return metadata_result
        else:
            if verbose:
                print(f"Both ISRC and metadata resolution failed")
            return None

# Convenience function
def smart_resolve_track(track: Dict, verbose: bool = False) -> Optional[Dict]:
    """
    Smart resolve track dengan fallback logic
    
    Args:
        track: Dictionary dengan track metadata
        verbose: Debug output
        
    Returns:
        Resolved track dict atau None
    """
    resolver = SmartResolver()
    return resolver.resolve_track(track, verbose)

# Test function
def test_smart_resolver():
    """Test smart resolver dengan problematic tracks"""
    
    test_tracks = [
        {
            'title': 'Save Me',
            'artist': 'Chief Keef',
            'album': 'Feed The Streets',
            'duration_ms': 188252,
            'isrc': 'QM6N21423734'  # ISRC available
        },
        {
            'title': 'BLAMMER',
            'artist': 'LAZER DIM 700',
            'album': 'DISASTER',
            'duration_ms': 169952,
            'isrc': 'QZHN92381546'  # ISRC available
        },
        {
            'title': 'Princess',
            'artist': 'Feng',
            'album': '',
            'duration_ms': 87000,
            'isrc': None  # No ISRC
        }
    ]
    
    print("TESTING SMART RESOLVER")
    print("=" * 60)
    
    for i, track in enumerate(test_tracks, 1):
        print(f"\n{i}. {track['title']} by {track['artist']}")
        print(f"   ISRC: {track['isrc'] or 'None'}")
        print("-" * 40)
        
        result = smart_resolve_track(track, verbose=True)
        
        if result:
            confidence = result.get('confidence', 0)
            print(f"RESOLVED: {result.get('title')} - {confidence:.2f} confidence")
        else:
            print(f"FAILED to resolve")
        
        print()

if __name__ == "__main__":
    test_smart_resolver()
