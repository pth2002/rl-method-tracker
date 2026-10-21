"""Write docs/hero.svg and docs/hero-dark.svg, the animated header of the README, and docs/og.png.

  python tools/site_hero.py         (after tools/site_data.py; tools/update.py runs both)
  python tools/site_hero.py --png   (also redraw docs/og.png when the header did not change)

The image replays the opening of the project page: the papers rise month by month, the ones whose
method reached a framework light up, and those later removed from every framework turn red. The
animation is CSS inside the SVG and runs once. A viewer who asks for reduced motion, or a client
that does not run SVG animation, sees the final frame.

An SVG shown as an image cannot load fonts, so the text is drawn as glyph outlines. tools/fonts holds
Big Shoulders Display and JetBrains Mono cut down to printable ASCII and the middle dot, under the
SIL Open Font License (OFL-*.txt). The output depends only on the data and these files, so an
unchanged tracker writes identical images.
"""
from __future__ import annotations

import json
import math
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

ROOT = Path(__file__).resolve().parents[1]
FONTS = ROOT / "tools" / "fonts"
W, H, PAD = 1280, 640, 64

THEMES = {
    "hero.svg": {"bg": "#F5F6F8", "ink": "#16181D", "muted": "#5B6270", "dot": "#CDD2D9",
                 "lit": "#128A43", "red": "#C4322B"},
    "hero-dark.svg": {"bg": "#0D1117", "ink": "#E7E9ED", "muted": "#9AA1AD", "dot": "#30363F",
                      "lit": "#3CC074", "red": "#F0675D"},
}


def font(family: str, weight: int) -> TTFont:
    return TTFont(FONTS / f"{family.replace(' ', '')}-{weight}-subset.ttf")


def num(v: float) -> str:
    return f"{v:.1f}".rstrip("0").rstrip(".")


def text_width(f: TTFont, text: str, size: float, tracking: float = 0.0) -> float:
    cmap, hmtx, s = f.getBestCmap(), f["hmtx"], size / f["head"].unitsPerEm
    return sum(hmtx[cmap[ord(c)]][0] * s + tracking for c in text) - tracking


def outline(f: TTFont, text: str, x: float, y: float, size: float, tracking: float = 0.0) -> str:
    """SVG path data for text set at baseline y, starting at x."""
    glyphs, cmap, hmtx = f.getGlyphSet(), f.getBestCmap(), f["hmtx"]
    s = size / f["head"].unitsPerEm
    pen = SVGPathPen(glyphs, ntos=num)
    for c in text:
        g = cmap[ord(c)]
        glyphs[g].draw(TransformPen(pen, (s, 0, 0, -s, x, y)))
        x += hmtx[g][0] * s + tracking
    return pen.getCommands()


def build(papers: list, counts: dict, colors: dict, fonts: dict) -> str:
    display, mono, mono_bold = fonts["display"], fonts["mono"], fonts["mono_bold"]
    size, track = 76, -0.76
    line1 = f"{counts['general']:,} RL training methods on arXiv."
    n_inc = f"{counts['included']}"
    note = "seven open-source RL frameworks · Jan 2025 to Jun 2026"
    x37 = PAD + text_width(display, n_inc, size, track) + track
    texts = [
        ("ink", "", outline(mono_bold, "rl-method-tracker", PAD, 74, 18)),
        ("muted", "", outline(mono, note, W - PAD - text_width(mono, note, 18), 74, 18)),
        ("muted", "", outline(display, line1, PAD, 171, size, track)),
        ("lit", "l2", outline(display, n_inc, PAD, 242, size, track)),
        ("ink", "l2", outline(display, " reached framework code.", x37, 242, size, track)),
    ]

    # the dot field: one column per month, included papers at the bottom
    months = sorted({p[1] for p in papers})
    cols = [sorted((p for p in papers if p[1] == m), key=lambda p: (-p[3], p[0])) for m in months]
    k, gap, fw, fh = 7, 1.6, W - 2 * PAD, 300
    pitch = min(fw / (len(months) * k + (len(months) - 1) * gap), fh / math.ceil(max(map(len, cols)) / k))
    col_w = (k + gap) * pitch
    x0 = PAD + (fw - (len(months) * col_w - gap * pitch)) / 2
    y0 = H - 44
    r = num(pitch * 0.36)
    bands, lit_i = [], 0
    for c, col in enumerate(cols):
        by_band: dict[int, list[str]] = {}
        for j, p in enumerate(col):
            cx, cy = x0 + c * col_w + (j % k + 0.5) * pitch, y0 - (j // k + 0.5) * pitch
            if p[3]:
                cls = "g" if p[4] else "x"
                circle = (f'<circle class="{cls}" style="animation-delay:{1450 + lit_i * 28}ms" '
                          f'cx="{num(cx)}" cy="{num(cy)}" r="{r}"/>')
                lit_i += 1
            else:
                circle = f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{r}"/>'
            by_band.setdefault(j // (3 * k), []).append(circle)
        for b, circles in by_band.items():
            bands.append(f'<g class="b" style="animation-delay:{c * 55 + b * 25}ms">{"".join(circles)}</g>')

    c = colors
    style = f"""
circle{{fill:{c['dot']}}}
.g{{fill:{c['lit']};animation:light .5s ease backwards}}
.x{{fill:{c['red']};animation:fall 1.6s ease backwards}}
.b{{animation:rise .45s cubic-bezier(.2,.7,.2,1) backwards}}
.l2{{animation:fade .6s ease 2.2s backwards}}
@keyframes rise{{from{{opacity:0;transform:translateY(8px)}}}}
@keyframes light{{from{{fill:{c['dot']}}}}}
@keyframes fall{{0%{{fill:{c['dot']}}}30%,65%{{fill:{c['lit']}}}}}
@keyframes fade{{from{{opacity:0}}}}
@media (prefers-reduced-motion:reduce){{*{{animation:none!important}}}}
"""
    paths = "".join(f'<path class="{cls}" fill="{c[col]}" d="{d}"/>' for col, cls, d in texts)
    alt = f"{line1} {n_inc} reached framework code."
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
            f'role="img" aria-label="{alt}"><title>{alt}</title><style>{style}</style>'
            f'<rect width="{W}" height="{H}" fill="{c["bg"]}"/>{paths}{"".join(bands)}</svg>\n')


def find_chrome() -> str | None:
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome"):
        if shutil.which(name):
            return shutil.which(name)
    for p in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
              r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"):
        if Path(p).exists():
            return p
    return None


def render_png(svg: Path, png: Path) -> bool:
    """Screenshot the final frame of svg into png with a headless Chromium browser."""
    chrome = find_chrome()
    if not chrome:
        return False
    with tempfile.TemporaryDirectory() as profile:
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
                        f"--user-data-dir={profile}", "--force-prefers-reduced-motion",
                        f"--window-size={W},{H}", "--virtual-time-budget=2000",
                        f"--screenshot={png}", svg.resolve().as_uri()],
                       capture_output=True, timeout=120)
    return png.exists()


def main() -> None:
    src = (ROOT / "docs" / "data.js").read_text(encoding="utf-8")
    data = json.loads(src[src.index("{"):src.rindex("}") + 1])
    fonts = {"display": font("Big Shoulders Display", 800), "mono": font("JetBrains Mono", 400),
             "mono_bold": font("JetBrains Mono", 500)}
    changed = False
    for name, colors in THEMES.items():
        out = ROOT / "docs" / name
        svg = build(data["papers"], data["counts"], colors, fonts)
        new = not out.exists() or out.read_text(encoding="utf-8") != svg
        if new:
            out.write_text(svg, encoding="utf-8", newline="\n")
            changed = True
        print(f"docs/{name}: {'rewritten' if new else 'unchanged'}, {out.stat().st_size // 1024} KB")
    # docs/og.png is the link preview of the project page: the light header's final frame. It is
    # redrawn only when the header changes, so browser updates alone never touch it.
    og = ROOT / "docs" / "og.png"
    if changed or "--png" in sys.argv or not og.exists():
        print("docs/og.png:", "redrawn" if render_png(ROOT / "docs" / "hero.svg", og)
              else "kept, no headless Chromium found")


if __name__ == "__main__":
    main()
