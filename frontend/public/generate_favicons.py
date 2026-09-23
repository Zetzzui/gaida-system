"""
generate_favicons.py
─────────────────────────────────────────────────────────────
Regenerates the GAIDA favicon assets (favicon.svg + favicon.ico)
from the updated v2 icon design so they always match the PWA icons.

The v2 design is defined inline here (same art as generate_icons_v2.py)
because that script's draw function isn't importable as a module.

Outputs (overwrites in place):
    frontend/public/icons/favicon.svg
    frontend/public/icons/favicon.ico
    frontend/public/favicon.ico        (same ico, kept at public root)
"""
import base64
import io
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent  # frontend/public


def draw_gaida_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    p = s / 512

    # Rounded rect background
    r = int(88 * p)
    draw.rounded_rectangle([0, 0, s, s], radius=r, fill=(11, 9, 22, 255))

    # Subtle outer glow
    for radius, alpha in [(178 * p, 20), (168 * p, 15)]:
        draw.ellipse([s / 2 - radius, s / 2 - radius, s / 2 + radius, s / 2 + radius],
                     fill=(100, 82, 220, alpha))

    # Main circle layers — deep purple sphere
    layers = [
        (155 * p, (38, 28, 95, 255)),
        (148 * p, (52, 40, 130, 255)),
        (140 * p, (66, 50, 162, 255)),
        (134 * p, (78, 60, 185, 255)),
        (128 * p, (88, 68, 200, 255)),
    ]
    for radius, color in layers:
        draw.ellipse([s / 2 - radius, s / 2 - radius, s / 2 + radius, s / 2 + radius],
                     fill=color)

    # Highlight shimmer top-left of circle
    draw.ellipse([s / 2 - 78 * p, s / 2 - 90 * p, s / 2 - 10 * p, s / 2 - 30 * p],
                 fill=(255, 255, 255, 14))

    # ── G letterform ─────────────────────────────────────────────
    cx, cy = s / 2, s / 2
    white = (255, 255, 255, 255)

    arc_r = 76 * p          # center radius of stroke
    stroke_w = int(16 * p)  # half-stroke width for arc

    # G arc: from ~55° to ~360° going clockwise (opening at top-right)
    draw.arc(
        [cx - arc_r - stroke_w, cy - arc_r - stroke_w,
         cx + arc_r + stroke_w, cy + arc_r + stroke_w],
        start=310,
        end=300,
        fill=white,
        width=stroke_w * 2
    )

    # Crossbar — middle-right of the G
    bar_top = int(cy - stroke_w * 0.9)
    bar_bot = int(cy + stroke_w * 0.9)
    bar_left = int(cx - stroke_w * 0.3)
    bar_right = int(cx + arc_r - stroke_w * 0.5)
    draw.rectangle([bar_left, bar_top, bar_right, bar_bot], fill=white)

    # Round the left end of the crossbar
    draw.ellipse([bar_left - stroke_w * 0.8, bar_top,
                  bar_left + stroke_w * 0.8, bar_bot], fill=white)

    # Accent dot — lower right, small pulse indicator
    dot_cx = int(cx + 105 * p)
    dot_cy = int(cy + 88 * p)
    for r2, c2 in [
        (16 * p, (130, 100, 255, 180)),
        (10 * p, (180, 160, 255, 255)),
        (5 * p, (230, 220, 255, 255)),
    ]:
        draw.ellipse([dot_cx - r2, dot_cy - r2, dot_cx + r2, dot_cy + r2], fill=c2)

    return img


def png_bytes(img) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return buf.getvalue()


def write_favicon_svg(dest: Path, img: Image.Image):
    """Emits a RealFaviconGenerator-style SVG with the PNG embedded as base64."""
    b64 = base64.b64encode(png_bytes(img)).decode('ascii')
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" version="1.1" '
        'xmlns:xlink="http://www.w3.org/1999/xlink" width="225" height="225" '
        'viewBox="0 0 225 225">'
        '<metadata><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/">'
        '<rdf:Description><dc:creator>GAIDA — generated from v2 icon design</dc:creator>'
        '</rdf:Description></rdf:RDF></metadata>'
        f'<image width="225" height="225" xlink:href="data:image/png;base64,{b64}"/>'
        '</svg>'
    )
    dest.write_text(svg, encoding='utf-8')
    print(f"OK {dest}")


def write_favicon_ico(dest: Path, img: Image.Image):
    img.save(dest, format='ICO', sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"OK {dest}")


def main():
    base = draw_gaida_icon(225)         # for the SVG favicon
    write_favicon_svg(ROOT / 'icons' / 'favicon.svg', base)

    ico = draw_gaida_icon(64)           # source for .ico (resized internally)
    write_favicon_ico(ROOT / 'icons' / 'favicon.ico', ico)
    write_favicon_ico(ROOT / 'favicon.ico', ico)  # keep public-root copy in sync


if __name__ == '__main__':
    main()