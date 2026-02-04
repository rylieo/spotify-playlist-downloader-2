def build_query(track, use_official=True):
    """Build a YouTube search query from track metadata."""
    # We now keep it clean and let downloader.py try variants if needed
    return f'{track["title"]} {track["artist"]}'
