from PIL import Image, ImageDraw
import math

def draw_gaida_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    p = s / 512

    # Rounded rect background
    r = int(88 * p)
    draw.rounded_rectangle([0, 0, s, s], radius=r, fill=(11, 9, 22, 255))

    # Subtle outer glow
    for radius, alpha in [(178*p, 20), (168*p, 15)]:
        draw.ellipse([s/2 - radius, s/2 - radius, s/2 + radius, s/2 + radius],
                     fill=(100, 82, 220, alpha))

    # Main circle layers — deep purple sphere
    layers = [
        (155*p, (38, 28, 95, 255)),
        (148*p, (52, 40, 130, 255)),
        (140*p, (66, 50, 162, 255)),
        (134*p, (78, 60, 185, 255)),
        (128*p, (88, 68, 200, 255)),
    ]
    for radius, color in layers:
        draw.ellipse([s/2 - radius, s/2 - radius, s/2 + radius, s/2 + radius],
                     fill=color)

    # Highlight shimmer top-left of circle
    draw.ellipse([s/2 - 78*p, s/2 - 90*p, s/2 - 10*p, s/2 - 30*p],
                 fill=(255, 255, 255, 14))

    # ── G letterform ─────────────────────────────────────────────
    cx, cy = s / 2, s / 2
    white = (255, 255, 255, 255)

    # Arc parameters
    arc_r = 76 * p          # center radius of stroke
    stroke_w = int(16 * p)  # half-stroke width for arc

    # Draw G arc: from ~55° to ~360° going clockwise (PIL convention)
    # PIL arc: 0=3 o'clock, goes clockwise
    # We want opening at top-right (~1 o'clock position)
    draw.arc(
        [cx - arc_r - stroke_w, cy - arc_r - stroke_w,
         cx + arc_r + stroke_w, cy + arc_r + stroke_w],
        start=310,   # start at ~1 o'clock (leaving gap)
        end=300,     # almost full circle
        fill=white,
        width=stroke_w * 2
    )

    # Crossbar — middle-right of the G
    # Starts at center-x, ends at arc right edge, sits at middle height
    bar_top = int(cy - stroke_w * 0.9)
    bar_bot = int(cy + stroke_w * 0.9)
    bar_left = int(cx - stroke_w * 0.3)
    bar_right = int(cx + arc_r - stroke_w * 0.5)
    draw.rectangle([bar_left, bar_top, bar_right, bar_bot], fill=white)

    # Round the left end of the crossbar
    draw.ellipse([bar_left - stroke_w*0.8, bar_top,
                  bar_left + stroke_w*0.8, bar_bot], fill=white)

    # Accent dot — lower right, small pulse indicator
    dot_cx = int(cx + 105 * p)
    dot_cy = int(cy + 88 * p)
    for r2, c2 in [
        (16*p, (130, 100, 255, 180)),
        (10*p, (180, 160, 255, 255)),
        (5*p,  (230, 220, 255, 255)),
    ]:
        draw.ellipse([dot_cx - r2, dot_cy - r2, dot_cx + r2, dot_cy + r2], fill=c2)

    return img


sizes = [72, 96, 128, 144, 152, 192, 384, 512]

for size in sizes:
    icon = draw_gaida_icon(size)
    path = f"/mnt/user-data/outputs/gaida-icons/icon-{size}x{size}.png"
    icon.save(path, 'PNG')
    print(f"✓ icon-{size}x{size}.png")

favicon = draw_gaida_icon(32)
favicon.save("/mnt/user-data/outputs/gaida-icons/favicon-32x32.png", 'PNG')
print("✓ favicon-32x32.png")
