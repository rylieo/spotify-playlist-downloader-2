def clean_metadata(tracks_or_tuple):
    # Handle both tracks list and tuple (tracks, playlist_name)
    if isinstance(tracks_or_tuple, tuple) or isinstance(tracks_or_tuple, list):
        if len(tracks_or_tuple) == 2 and isinstance(tracks_or_tuple[0], list):
            tracks = tracks_or_tuple[0]
        else:
            tracks = tracks_or_tuple
    else:
        tracks = tracks_or_tuple
    
    clean = []
    for t in tracks:
        clean.append(
            {
                "title": t["title"],
                "artist": t["artist"],
                "album": t["album"],
                "album_artist": t["album_artist"],
                "year": t["year"],
                "duration_ms": t.get("duration_ms", 0),
                "track_number": t["track_number"],
                "genre": t["genre"],
                "isrc": t.get("isrc", ""),  # Tambahkan ISRC!
                "cover_url": t["cover_url"],
            }
        )
    return clean
