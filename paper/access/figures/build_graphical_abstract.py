"""Draw a conceptual, data-free IEEE Access graphical-abstract draft."""

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math


OUT = Path(__file__).with_name("graphical_abstract_draft.png")
W, H = 1320, 590
im = Image.new("RGB", (W, H), "#f7fafc")
d = ImageDraw.Draw(im)
font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
title = ImageFont.truetype(bold_path, 29)
label = ImageFont.truetype(bold_path, 18)
small = ImageFont.truetype(font_path, 16)
tiny = ImageFont.truetype(font_path, 14)


def centered(text, x0, x1, y, font, fill="#17334c"):
    box = d.textbbox((0, 0), text, font=font)
    d.text(((x0 + x1 - box[2]) / 2, y), text, font=font, fill=fill)


def box(x, heading, sub, color="#eaf2f7"):
    d.rounded_rectangle((x, 115, x + 190, 390), radius=18, fill=color,
                        outline="#9db1c0", width=2)
    centered(heading, x + 8, x + 182, 135, label)
    centered(sub, x + 8, x + 182, 167, small, "#4a6071")


def arrow(x):
    cy = 252
    d.line((x, cy, x + 21, cy), fill="#276b8c", width=5)
    d.polygon([(x + 28, cy), (x + 18, cy - 9), (x + 18, cy + 9)],
              fill="#276b8c")


centered("Decoder-aligned frequency impairment to observed robustness", 0, W, 35,
         title)
xs = [35, 250, 465, 680, 895, 1110]
for x, heading, sub, shade in zip(
    xs,
    ["Frequency", "Project out", "Residual", "Severity", "Production", "Decode"],
    ["trajectory", "constant + linear", "r_f(t)", "RMS / shape", "WSJT-X wsprd", "boundary"],
    ["#e5f2f8", "#eaf3f3", "#e7f1ed", "#edf3e5", "#e7edf6", "#f0ebf6"],
):
    box(x, heading, sub, shade)
for x in [225, 440, 655, 870, 1085]:
    arrow(x + 2)

# Frequency-transient and fitted-line sketches (conceptual, not measured data).
for x, offset in [(35, 0), (250, 0)]:
    d.line((x + 23, 336, x + 167, 336), fill="#94a9b7", width=2)
    d.line((x + 23, 218, x + 23, 336), fill="#94a9b7", width=2)
    pts = []
    for k in range(85):
        u = k / 84
        y = 317 - 75 * (1 - math.exp(-3.5 * u)) + 10 * math.sin(6 * u)
        pts.append((x + 25 + 140 * u, y + offset))
    d.line(pts, fill="#096994", width=4, joint="curve")
    if x == 250:
        d.line((x + 25, 307, x + 165, 241), fill="#bf693f", width=3)

# Orthogonal residual sketch.
x = 465
d.line((x + 23, 275, x + 168, 275), fill="#94a9b7", width=2)
d.line([(x + 25 + k * 1.65,
         275 + 30 * math.cos(2 * math.pi * k / 87)) for k in range(88)],
       fill="#238067", width=4, joint="curve")

# A compact RMS-bar / shape reminder.
x = 680
for j, height in enumerate([30, 55, 74, 48, 32]):
    bx = x + 33 + j * 29
    d.rounded_rectangle((bx, 340 - height, bx + 17, 340), radius=4,
                        fill="#70a465")
d.line((x + 26, 341, x + 167, 341), fill="#94a9b7", width=2)

# Decoder block icon.
x = 895
d.rounded_rectangle((x + 38, 224, x + 152, 338), radius=12,
                    fill="#274c72")
for j in range(3):
    d.ellipse((x + 52 + j * 30, 245, x + 63 + j * 30, 256),
              fill="#a7dce6")
d.line((x + 54, 290, x + 136, 290), fill="#bed7e9", width=4)
d.line((x + 54, 307, x + 121, 307), fill="#bed7e9", width=4)

# Only a qualitative decode-boundary icon: narrower tolerance at lower SNR.
x = 1110
d.line((x + 31, 339, x + 166, 339), fill="#94a9b7", width=2)
d.line((x + 31, 222, x + 31, 339), fill="#94a9b7", width=2)
d.line([(x + 35, 247), (x + 76, 252), (x + 114, 285), (x + 162, 326)],
       fill="#7555a8", width=5, joint="curve")
centered("SNR threshold", x + 12, x + 180, 348, tiny, "#4a6071")

d.rounded_rectangle((36, 431, W - 36, 540), radius=17, fill="#ffffff",
                    outline="#cad8e1", width=2)
centered("Observed within tested grids", 36, W - 36, 446, label)
centered("Near-threshold tolerance contracts; trajectory families need not map identically",
         36, W - 36, 483, small, "#4a6071")

im.save(OUT, optimize=True)
print(OUT)
