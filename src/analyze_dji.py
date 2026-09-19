"""Probe DJI's official D-Log2 -> Rec.709 LUT to recover its behaviour.

DJI never published a D-Log2 white paper, so the 65-cube they ship is the
only public sample of their colour science. We measure it rather than
guess: neutral tone response, black/white anchors, where 18% grey lands,
saturation response, and channel crosstalk.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from lutlib import read_cube, sample_cube  # noqa: E402

VENDOR = os.path.join(os.path.dirname(__file__), "..", "vendor")
STD = os.path.join(VENDOR, "DJI_OSMO_Pocket_4P_D-Log2_to_Rec709_V1.0_size65.cube")
VIV = os.path.join(VENDOR, "DJI_OSMO_Pocket_4P_D-Log2_to_Rec709_vivid_V1.0_size65.cube")


def rec709_eotf(v):
    """BT.1886-ish: display-linear from Rec.709 code value (gamma 2.4)."""
    return np.power(np.clip(v, 0.0, None), 2.4)


def describe(path, label):
    table, size, dmin, dmax = read_cube(path)
    print(f"\n{'=' * 68}\n{label}\n  {os.path.basename(path)}")
    print(f"  size={size}  domain={dmin}..{dmax}")

    n = 33
    x = np.linspace(0.0, 1.0, n)
    neutral = sample_cube(table, np.stack([x, x, x], axis=-1))

    print(f"\n  neutral axis (D-Log2 in -> Rec.709 out), {n} samples")
    print(f"  {'in':>7} {'in10':>5} | {'R':>8} {'G':>8} {'B':>8} | "
          f"{'out10':>5} {'lin':>8}")
    for i in range(n):
        o = neutral[i]
        lin = rec709_eotf(o.mean())
        print(f"  {x[i]:7.4f} {x[i] * 1023:5.0f} | {o[0]:8.5f} {o[1]:8.5f} "
              f"{o[2]:8.5f} | {o.mean() * 1023:5.0f} {lin:8.5f}")

    # anchors
    print("\n  anchors")
    for name, cv10 in [("black (CV 64)", 64), ("18% grey (CV ~312)", 312),
                       ("CV 400", 400), ("CV 512", 512),
                       ("90% white (CV ~600?)", 600), ("CV 700", 700),
                       ("CV 940", 940), ("CV 1023", 1023)]:
        v = cv10 / 1023.0
        o = sample_cube(table, np.array([v, v, v]))
        print(f"    {name:22s} in={v:.4f} -> out={o.mean():.5f} "
              f"({o.mean() * 1023:6.1f} CV10, {o.mean() * 100:5.1f} IRE)")

    # where does the LUT put its own black and white?
    lo = sample_cube(table, np.array([0.0, 0.0, 0.0]))
    hi = sample_cube(table, np.array([1.0, 1.0, 1.0]))
    print(f"\n    LUT black out = {lo}  white out = {hi}")

    # contrast: local slope in stops
    xs = np.linspace(0.02, 0.98, 200)
    ns = sample_cube(table, np.stack([xs, xs, xs], axis=-1)).mean(axis=-1)
    slope = np.gradient(ns, xs)
    peak = int(np.argmax(slope))
    print(f"    max slope {slope[peak]:.3f} at in={xs[peak]:.4f} "
          f"(CV {xs[peak] * 1023:.0f})")
    # first/last input where output is still moving meaningfully
    moving = np.where(slope > 0.02)[0]
    print(f"    output responds from in={xs[moving[0]]:.4f} "
          f"to in={xs[moving[-1]]:.4f} "
          f"(CV {xs[moving[0]] * 1023:.0f}..{xs[moving[-1]] * 1023:.0f})")

    # saturation behaviour on primaries and skin-ish patches
    print("\n  patch response (in -> out)")
    patches = {
        "log grey 0.30": (0.30, 0.30, 0.30),
        "log red": (0.70, 0.30, 0.30),
        "log green": (0.30, 0.70, 0.30),
        "log blue": (0.30, 0.30, 0.70),
        "log skin-ish": (0.44, 0.36, 0.32),
        "log sky-ish": (0.34, 0.40, 0.50),
        "log foliage": (0.32, 0.42, 0.30),
        "highlight warm": (0.80, 0.72, 0.62),
    }
    for name, p in patches.items():
        o = sample_cube(table, np.array(p))
        mx, mn = o.max(), o.min()
        sat = 0.0 if mx <= 0 else (mx - mn) / mx
        print(f"    {name:16s} {p} -> ({o[0]:.4f}, {o[1]:.4f}, {o[2]:.4f})  "
              f"sat={sat:.3f}")
    return table, size


def compare(a, b, size):
    print(f"\n{'=' * 68}\nstandard vs vivid")
    xs = np.linspace(0.0, 1.0, 17)
    na = sample_cube(a, np.stack([xs, xs, xs], -1)).mean(-1)
    nb = sample_cube(b, np.stack([xs, xs, xs], -1)).mean(-1)
    print(f"  {'in':>7} | {'std':>8} {'vivid':>8} {'delta':>8}")
    for i in range(len(xs)):
        print(f"  {xs[i]:7.4f} | {na[i]:8.5f} {nb[i]:8.5f} "
              f"{nb[i] - na[i]:+8.5f}")

    rng = np.random.default_rng(7)
    pts = rng.random((4000, 3)) * 0.7 + 0.15
    oa = sample_cube(a, pts)
    ob = sample_cube(b, pts)

    def sat(o):
        mx = o.max(-1)
        mn = o.min(-1)
        return np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)

    print(f"\n  mean saturation  std={sat(oa).mean():.4f}  "
          f"vivid={sat(ob).mean():.4f}  "
          f"ratio={sat(ob).mean() / max(sat(oa).mean(), 1e-9):.3f}")


if __name__ == "__main__":
    ta, size = describe(STD, "DJI official — D-Log2 to Rec.709 (standard)")
    tb, _ = describe(VIV, "DJI official — D-Log2 to Rec.709 (vivid)")
    compare(ta, tb, size)
