"""Measure every look against a real frame, so tuning is not eyeballing.

  python src/measure_looks.py frame.png [--size 65]

Reports per LUT:
  neutral cast  how much a surface that is neutral in the log source gets
                tinted. A look may tint on purpose, but "Natural" doing
                6% is a bug, not a look.
  skin          hue angle, saturation and luma of detected skin. Skin is
                the thing an audience notices first, so it gets its own
                column rather than being averaged away.
  black/white   where the look puts its darkest and brightest values.
"""
from __future__ import annotations

import argparse
import glob
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(__file__))
from lutlib import read_cube, sample_cube  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def hue_sat(rgb):
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    d = mx - mn
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    with np.errstate(invalid="ignore", divide="ignore"):
        h = np.where(mx == r, ((g - b) / np.where(d > 0, d, 1)) % 6.0,
                     np.where(mx == g, (b - r) / np.where(d > 0, d, 1) + 2.0,
                              (r - g) / np.where(d > 0, d, 1) + 4.0)) * 60.0
    return np.where(d > 1e-6, h, 0.0), np.where(mx > 1e-6, d / mx, 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("frame")
    ap.add_argument("--size", type=int, default=65)
    a = ap.parse_args()

    src = np.asarray(Image.open(a.frame).convert("RGB")).astype(np.float64)
    src /= 255.0
    _, sat = hue_sat(src)
    lum = src.mean(-1)

    neutral = (sat < 0.020) & (lum > np.percentile(lum, 60))
    npix = src[neutral][::37]

    files = sorted(glob.glob(os.path.join(ROOT, "luts",
                                          f"*_size{a.size}.cube")))
    ref = [f for f in files if "Neutral" in f][0]
    t, _, _, _ = read_cube(ref)
    full = sample_cube(t, src[::3, ::3])
    h, s = hue_sat(full)
    L = full.mean(-1)
    skin = (h > 8) & (h < 40) & (s > 0.13) & (s < 0.55) & (L > 0.30) & (L < 0.80)
    spix = src[::3, ::3][skin]
    if len(spix) > 4000:
        spix = spix[:: len(spix) // 4000]

    print(f"frame {os.path.basename(a.frame)}   "
          f"neutral px {neutral.sum()} ({100 * neutral.mean():.1f}%)   "
          f"skin px {skin.sum()} ({100 * skin.mean():.1f}%)")
    print(f"\n{'LUT':20s} {'neutral':>8} {'skin hue':>9} {'skin sat':>9} "
          f"{'skin lum':>9} {'p1':>6} {'p99':>6}")
    for f in files:
        t, _, _, _ = read_cube(f)
        o = sample_cube(t, npix)
        cast = ((o.max(-1) - o.min(-1)) / np.maximum(o.max(-1), 1e-6)).mean()
        so = sample_cube(t, spix)
        sh, ss = hue_sat(so)
        # circular mean so hues near 0/360 do not average to nonsense
        ang = np.deg2rad(sh)
        mh = np.rad2deg(np.arctan2(np.sin(ang).mean(), np.cos(ang).mean())) % 360
        allo = sample_cube(t, src[::5, ::5]).mean(-1)
        name = os.path.basename(f).replace("P4P_", "").replace(
            f"_size{a.size}.cube", "")
        print(f"  {name:18s} {cast * 100:7.2f}% {mh:8.1f}d {ss.mean():9.3f} "
              f"{so.mean():9.3f} {np.percentile(allo, 1):6.3f} "
              f"{np.percentile(allo, 99):6.3f}")


if __name__ == "__main__":
    main()
