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

    # MP3 / ID3
    if ext == ".mp3":
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
        return

    # M4A / MP4 (AAC)
    if ext in (".m4a", ".mp4", ".aac"):
        audio = MP4(path)
        audio.tags["\xa9nam"] = [_safe_get(meta, "title")]
        audio.tags["\xa9ART"] = [_safe_get(meta, "artist")]
        audio.tags["\xa9alb"] = [_safe_get(meta, "album")]
        if _safe_get(meta, "album_artist"):
            audio.tags["aART"] = [_safe_get(meta, "album_artist")]
        audio.tags["trkn"] = [(int(_safe_get(meta, "track_number") or 0), 0)]
        if _safe_get(meta, "year"):
            audio.tags["\xa9day"] = [_safe_get(meta, "year")]
        if _safe_get(meta, "genre"):
            audio.tags["\xa9gen"] = [_safe_get(meta, "genre")]

        with open(cover_path, "rb") as img:
            audio.tags["covr"] = [
                MP4Cover(img.read(), imageformat=MP4Cover.FORMAT_JPEG)
            ]

        audio.save()

        audio = MP4(path)
        if not audio.tags or "covr" not in audio.tags:
            raise RuntimeError(
                "Tagging verification failed: no covr frames found after save"
            )
        return

    # OGG / Vorbis
    if ext == ".ogg":
        audio = OggVorbis(path)
        audio["title"] = [_safe_get(meta, "title")]
        audio["artist"] = [_safe_get(meta, "artist")]
        audio["album"] = [_safe_get(meta, "album")]
        if _safe_get(meta, "album_artist"):
            audio["albumartist"] = [_safe_get(meta, "album_artist")]
        if _safe_get(meta, "year"):
            audio["date"] = [_safe_get(meta, "year")]
        if _safe_get(meta, "genre"):
            audio["genre"] = [_safe_get(meta, "genre")]
        audio["tracknumber"] = [str(_safe_get(meta, "track_number"))]

        # Embed cover using METADATA_BLOCK_PICTURE base64
        pic = Picture()
        pic.data = open(cover_path, "rb").read()
        pic.type = 3
        pic.mime = "image/jpeg"
        pic.desc = "Cover"
        pic_data = pic.write()
        audio["metadata_block_picture"] = [base64.b64encode(pic_data).decode("ascii")]

        audio.save()

        audio = OggVorbis(path)
        if not audio or "metadata_block_picture" not in audio:
            raise RuntimeError(
                "Tagging verification failed: no metadata_block_picture after save"
            )
        return

    # Unknown format
    raise RuntimeError(f"Unsupported audio format for tagging: {ext}")
