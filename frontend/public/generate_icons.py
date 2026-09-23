from PIL import Image, ImageDraw, ImageFont
import math

def draw_gaida_icon(size):
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    s = size
    p = s / 512

    # Rounded rect background - deep dark purple
    r = int(90 * p)
    bg_color = (13, 11, 26, 255)
    draw.rounded_rectangle([0, 0, s, s], radius=r, fill=bg_color)

    # Subtle glow ring behind main circle
    for i, alpha in [(175*p, 25), (165*p, 18), (158*p, 12)]:
        draw.ellipse([s//2 - i, s//2 - i, s//2 + i, s//2 + i],
                     fill=(124, 106, 247, alpha))

    # Main circle - layered for depth
    for radius, color in [
        (152*p, (40, 32, 100, 255)),
        (142*p, (58, 44, 148, 255)),
        (134*p, (72, 54, 172, 255)),
        (128*p, (82, 62, 190, 255)),
    ]:
        draw.ellipse([s//2 - radius, s//2 - radius, s//2 + radius, s//2 + radius],
                     fill=color)

    # Inner highlight shimmer
    draw.ellipse([s//2 - 70*p, s//2 - 80*p, s//2 + 10*p, s//2 - 20*p],
                 fill=(255, 255, 255, 18))

    # Draw "G" letterform
    cx, cy = s / 2, s / 2
    gr = 88 * p   # outer radius of G stroke
    gw = 17 * p   # stroke width
    white = (255, 255, 255, 255)

    # Draw G arc using thick polyline segments
    points_outer = []
    points_inner = []
    # Arc from ~50° to 360° (leaving gap at top-right)
    start_angle = 50
    end_angle = 360

    for deg in range(start_angle, end_angle + 1, 2):
        rad = math.radians(deg)
        # PIL uses clockwise from 3 o'clock; we convert
        ox = cx + gr * math.cos(math.radians(-deg + 90))
        oy = cy + gr * math.sin(math.radians(-deg + 90))
        ix = cx + (gr - gw*2) * math.cos(math.radians(-deg + 90))
        iy = cy + (gr - gw*2) * math.sin(math.radians(-deg + 90))
        points_outer.append((ox, oy))
        points_inner.append((ix, iy))

    # Draw G as thick arc
    draw.arc([cx - gr, cy - gr, cx + gr, cy + gr],
             start=start_angle - 90, end=end_angle - 90,
             fill=white, width=int(gw * 2))

    # G crossbar — horizontal bar from center going right
    bar_y = int(cy)
    bar_x1 = int(cx + 8*p)
    bar_x2 = int(cx + gr - 2*p)
    bar_h = int(gw)
    draw.rectangle([bar_x1, bar_y - bar_h, bar_x2, bar_y + bar_h], fill=white)

    # Small accent dot — bottom right
    dot_cx = int(cx + 100*p)
    dot_cy = int(cy + 85*p)
    draw.ellipse([dot_cx - 14*p, dot_cy - 14*p, dot_cx + 14*p, dot_cy + 14*p],
                 fill=(124, 106, 247, 255))
    draw.ellipse([dot_cx - 7*p, dot_cy - 7*p, dot_cx + 7*p, dot_cy + 7*p],
                 fill=(210, 205, 255, 255))

    return img


sizes = [72, 96, 128, 144, 152, 192, 384, 512]

for size in sizes:
    icon = draw_gaida_icon(size)
    path = f"/mnt/user-data/outputs/gaida-icons/icon-{size}x{size}.png"
    icon.save(path, 'PNG')
    print(f"✓ {path}")

# Also save a favicon-sized version
favicon = draw_gaida_icon(32)
favicon.save("/mnt/user-data/outputs/gaida-icons/favicon-32x32.png", 'PNG')
print("✓ favicon-32x32.png")

print("\nAll icons generated!")
