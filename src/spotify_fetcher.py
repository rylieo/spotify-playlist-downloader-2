import json, spotipy
import time
from spotipy.oauth2 import SpotifyClientCredentials


def fetch_playlist(playlist_url, config_path="config/spotify.json"):
    cfg = json.load(open(config_path))
    sp = spotipy.Spotify(
        auth_manager=SpotifyClientCredentials(
            client_id=cfg["client_id"], client_secret=cfg["client_secret"]
        )
    )

    # Use pagination to fetch all items (Spotify returns pages, ~100 items per page)
    # Added external_ids to fetch ISRC
    results = sp.playlist_items(playlist_url, fields="items.track(name,artists,album,duration_ms,external_ids),next,total")
    tracks = []

    while results and results.get("items"):
        for item in results["items"]:
            t = item.get("track")
            if not t:
                continue

            tracks.append(
                {
                    "title": t["name"],
                    "artist": t["artists"][0]["name"],
                    "album": t["album"]["name"],
                    "album_artist": t["album"]["artists"][0]["name"],
                    "year": t["album"].get("release_date", "")[:4],
                    "duration_ms": t.get("duration_ms", 0),
                    "track_number": len(tracks) + 1,
                    "genre": "Unknown",
                    "isrc": t.get("external_ids", {}).get("isrc"),
                    "cover_url": (
                        t["album"]["images"][0]["url"]
                        if t.get("album") and t["album"].get("images")
                        else ""
                    ),
                }
            )

        if results.get("next"):
            # follow the 'next' link using spotipy helper
            results = sp.next(results)
            # small delay to be polite to the API
            time.sleep(0.1)
        else:
            break

    # fetch playlist metadata (name) for post-run organization
    try:
        playlist_meta = sp.playlist(playlist_url, fields="name")
        playlist_name = playlist_meta.get("name") if playlist_meta else "playlist"
    except Exception:
        playlist_name = "playlist"

    json.dump(tracks, open("metadata_raw.json", "w", encoding="utf-8"), indent=2)
    return tracks, playlist_name
