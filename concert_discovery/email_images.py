"""Raster equivalents for table visuals that email clients cannot reliably style."""
import base64
import hashlib
import io
import re
from functools import lru_cache
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont


def data_url(image):
    buf = io.BytesIO()
    image.save(buf, format='PNG')
    return 'data:image/png;base64,' + base64.b64encode(buf.getvalue()).decode()


@lru_cache(maxsize=1)
def play_button():
    image = Image.new('RGBA', (116, 116))
    draw = ImageDraw.Draw(image)
    draw.ellipse((0, 0, 115, 115), fill='#102c43')
    draw.polygon([(46, 34), (46, 82), (82, 58)], fill='white')
    return data_url(image)


@lru_cache(maxsize=1)
def revival_icon():
    with Image.open(Path(__file__).parent / 'assets/revival.webp') as image:
        return data_url(image.convert('RGBA'))


def listener_bar(value, maximum, label):
    # Same 150 x 29 viewport and max-in-view scale as the website.
    image = Image.new('RGB', (600, 116), '#f4f6f8')
    draw = ImageDraw.Draw(image)
    width = round(max(0, min(1, (value or 0) / max(1, maximum))) * 600)
    if width:
        draw.rectangle((0, 0, width - 1, 115), fill='#bde6de')
    for font_path in ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf'):
        try:
            font = ImageFont.truetype(font_path, 56)
            break
        except OSError:
            continue
    else:
        font = ImageFont.load_default(size=56)
    draw.text((36, 58), label, font=font, fill='#102c43', anchor='lm')
    return data_url(image)


def inline_images(content):
    """Move raster visuals out of HTML into CID attachments; dedupe repeated images."""
    images = {}
    def replace(match):
        data = base64.b64decode(match.group(1))
        key = 'visual-' + hashlib.sha256(data).hexdigest()[:20]
        images[key] = data
        return 'cid:' + key
    return re.sub(r'data:image/png;base64,([A-Za-z0-9+/=]+)', replace, content), images
