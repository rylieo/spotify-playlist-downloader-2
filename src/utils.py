from PIL import Image
import requests
from io import BytesIO
import re


def sanitize_filename(name, replacement="_"):
    """Return a filesystem-safe filename by replacing or removing invalid characters."""
    # Remove control chars and replace reserved characters <>:"/\|?*
    sanitized = re.sub(r'[<>:"/\\|?*\x00-\x1f]', replacement, name)
    # Collapse multiple replacements
    sanitized = re.sub(rf"{re.escape(replacement)}+", replacement, sanitized)
    return sanitized.strip()


def process_cover(url, output_path):
    r = requests.get(url, timeout=10)
    r.raise_for_status()
    img = Image.open(BytesIO(r.content)).convert("RGB")
    img.thumbnail((500, 500))
    img.save(output_path, "JPEG", quality=85, optimize=True)
