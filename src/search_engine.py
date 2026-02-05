from .ytmusic_search import search_with_ytmusic

def build_query(track, use_official=True):
    """Build a YouTube search query from track metadata."""
    # We now keep it clean and let downloader.py try variants if needed
    # Including album name significantly improves finding the correct official version
    return f'{track["title"]} {track["artist"]} {track["album"]}'

def search_with_ytmusic_first(track, search_count=5, auth_file=None):
    """Search using YouTube Music API first, fallback to traditional search."""
    # Try YouTube Music search first
    ytmusic_results = search_with_ytmusic(track, auth_file, search_count)
    
    if ytmusic_results:
        return ytmusic_results
    
    # Fallback to traditional query building
    return None
