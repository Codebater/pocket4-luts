"""Render contact sheets: one source frame through every LUT in the pack.

  python src/preview.py <source.mp4 | frame.png> [--frames 3] [--size 33]
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), "..")
LUTS = os.path.join(ROOT, "luts")
OUTDIR = os.path.join(ROOT, "preview")


def _font(px):
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def extract_frames(src, n, tmp, width=960):
    os.makedirs(tmp, exist_ok=True)
    if src.lower().endswith((".png", ".jpg", ".jpeg", ".tif", ".tiff")):
        dst = os.path.join(tmp, "src_01.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", src,
                        "-vf", f"scale={width}:-2", dst], check=True)
        return [dst]
    dur = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", src],
        capture_output=True, text=True, check=True).stdout.strip())
    out = []
    for i in range(n):
        t = dur * (i + 1) / (n + 1)
        dst = os.path.join(tmp, f"src_{i + 1:02d}.png")
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}",
                        "-i", src, "-frames:v", "1",
                        "-vf", f"scale={width}:-2", dst], check=True)
        out.append(dst)
    return out


def apply_lut(frame, lut, dst):
    # forward slashes and escaped colon: ffmpeg's filter parser needs both
    safe = lut.replace("\\", "/").replace(":", "\\:")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", frame,
                    "-vf", f"lut3d=file='{safe}':interp=tetrahedral", dst],
                   check=True)


def sheet(frame, luts, dst, cols=4, label_h=34):
    tmp = tempfile.mkdtemp(prefix="p4plut_")
    try:
        tiles = [("SOURCE (D-Log2)", frame)]
        for lut in luts:
            name = os.path.basename(lut).replace(".cube", "")
            name = name.replace("P4P_", "").rsplit("_size", 1)[0]
            out = os.path.join(tmp, f"{name}.png")
            apply_lut(frame, lut, out)
            tiles.append((name.replace("_", "  "), out))

        w, h = Image.open(frame).size
        rows = (len(tiles) + cols - 1) // cols
        pad = 8
        sheet_img = Image.new(
            "RGB",
            (cols * w + (cols + 1) * pad,
             rows * (h + label_h) + (rows + 1) * pad),
            (16, 16, 18))
        draw = ImageDraw.Draw(sheet_img)
        font = _font(max(16, w // 42))
        for i, (name, path) in enumerate(tiles):
            r, c = divmod(i, cols)
            x = pad + c * (w + pad)
            y = pad + r * (h + label_h + pad)
            sheet_img.paste(Image.open(path).convert("RGB"), (x, y))
            draw.text((x + 4, y + h + 6), name,
                      font=font, fill=(228, 228, 232))
        sheet_img.save(dst, quality=93)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source")
    ap.add_argument("--frames", type=int, default=3)
    ap.add_argument("--size", type=int, default=33)
    ap.add_argument("--width", type=int, default=960)
    a = ap.parse_args()

    luts = sorted(glob.glob(os.path.join(LUTS, f"*_size{a.size}.cube")))
    if not luts:
        print(f"no size{a.size} LUTs in {LUTS}")
        return 1
    os.makedirs(OUTDIR, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="p4psrc_")
    try:
        frames = extract_frames(a.source, a.frames, tmp, a.width)
        for i, f in enumerate(frames, 1):
            dst = os.path.join(OUTDIR, f"contact_{i:02d}.jpg")
            sheet(f, luts, dst)
            print("wrote", dst)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
