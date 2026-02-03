def clean_metadata(tracks):
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
                "cover_url": t["cover_url"],
            }
        )
    return clean
