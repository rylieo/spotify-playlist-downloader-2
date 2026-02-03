def build_query(track, use_official=True):
    """Build a YouTube search query from track metadata.

    If use_official is True, append terms that bias toward official uploads.
    """
    base = f'{track["title"]} {track["artist"]}'
    if use_official:
        return f"{base} official audio"
    return base
