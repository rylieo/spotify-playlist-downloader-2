import os
import base64

from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TPE2, TRCK, TDRC, TCON
from mutagen.mp4 import MP4, MP4Cover
from mutagen.oggvorbis import OggVorbis
from mutagen.flac import Picture


def _safe_get(meta, key):
    v = meta.get(key)
    return v if v is not None else ""


def tag_audio(path, meta, cover_path):
    _, ext = os.path.splitext(path.lower())

    if ext != ".mp3":
        raise RuntimeError(f"Unsupported audio format for tagging: {ext}. Only MP3 is supported.")

    # MP2 / ID3
    audio = MP3(path, ID3=ID3)
    try:
        audio.add_tags()
    except Exception:
        pass

    audio.tags.add(TIT2(encoding=3, text=_safe_get(meta, "title")))
    audio.tags.add(TPE1(encoding=3, text=_safe_get(meta, "artist")))
    audio.tags.add(TALB(encoding=3, text=_safe_get(meta, "album")))
    audio.tags.add(TPE2(encoding=3, text=_safe_get(meta, "album_artist")))
    audio.tags.add(TRCK(encoding=3, text=str(_safe_get(meta, "track_number"))))
    audio.tags.add(TDRC(encoding=3, text=_safe_get(meta, "year")))
    audio.tags.add(TCON(encoding=3, text=_safe_get(meta, "genre")))

    with open(cover_path, "rb") as img:
        audio.tags.add(
            APIC(
                encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img.read()
            )
        )

    audio.save(v2_version=3)

    # verify
    audio = MP3(path, ID3=ID3)
    apics = audio.tags.getall("APIC") if audio.tags else []
    if not apics:
        raise RuntimeError(
            "Tagging verification failed: no APIC frames found after save"
        )
