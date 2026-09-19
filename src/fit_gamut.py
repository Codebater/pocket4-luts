"""Recover D-Gamut2 -> Rec.709 and the tone map hiding inside DJI's LUT.

DJI's official cube is a black box roughly of the form

    out = OETF709( RENDER( M . dlog2_to_linear(E) ) )

where M is the D-Gamut2 -> Rec.709 matrix. Both spaces are D65, so a
white-preserving M leaves the neutral axis alone, which means the neutral
tone render can be read straight off the neutral axis of the LUT.

M itself is recovered from the LUT's Jacobian at neutral, not by a global
curve fit. At a neutral point the chain rule gives

    d out_i / d E_j  =  OETF'(.) * RENDER'(.) * M_ij * (dx/dE)

and the leading factor is one scalar shared by every i and j. So the
Jacobian is M scaled row-uniformly, and since the rows of M sum to 1
(white in -> white out), simply normalising each Jacobian row by its own
sum returns M exactly. This holds whatever shape RENDER has, which is why
it succeeds where a global least-squares fit of a per-channel tone map
model does not.

Measuring it at several grey levels and checking the answers agree is the
built-in falsification test.
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from dlog2 import dlog2_to_linear  # noqa: E402
from lutlib import read_cube, sample_cube  # noqa: E402

VENDOR = os.path.join(os.path.dirname(__file__), "..", "vendor")
STD = os.path.join(VENDOR, "DJI_OSMO_Pocket_4P_D-Log2_to_Rec709_V1.0_size65.cube")

# reference matrices to compare the result against
BT2020_TO_709 = np.array([
    [1.66049, -0.58764, -0.07285],
    [-0.12455, 1.13290, -0.00835],
    [-0.01815, -0.10058, 1.11873]])
DGAMUT_TO_709 = np.array([          # DJI D-Gamut white paper (X7 / X9)
    [1.6746, -0.5797, -0.0949],
    [-0.0981, 1.3340, -0.2359],
    [-0.0410, -0.2430, 1.2840]])


def oetf709(lin):
    lin = np.clip(lin, 0.0, 1.0)
    return np.where(lin < 0.018, lin * 4.5,
                    1.099 * np.power(np.maximum(lin, 1e-12), 0.45) - 0.099)


def eotf709(v):
    v = np.clip(v, 0.0, 1.0)
    return np.where(v < 0.081, v / 4.5,
                    np.power((v + 0.099) / 1.099, 1.0 / 0.45))


class ToneMap:
    """DJI's neutral tone render, measured off the LUT: scene-linear in ->
    display-linear out, interpolated in log2 space."""

    def __init__(self, table, n=4096):
        e = np.linspace(0.0, 1.0, n)
        x = dlog2_to_linear(e)
        out = sample_cube(table, np.stack([e, e, e], -1)).mean(-1)
        y = eotf709(out)
        keep = x > 1e-6
        self.lx = np.log2(x[keep])
        self.y = np.maximum.accumulate(y[keep])

    def __call__(self, x):
        lx = np.log2(np.maximum(np.asarray(x, dtype=np.float64), 1e-10))
        return np.interp(lx, self.lx, self.y, left=0.0, right=self.y[-1])


def jacobian_at(table, e0, h=0.01):
    """Central-difference Jacobian of the LUT at neutral code e0."""
    base = np.array([e0, e0, e0])
    j = np.zeros((3, 3))
    for k in range(3):
        dp = base.copy(); dp[k] += h
        dm = base.copy(); dm[k] -= h
        j[:, k] = (sample_cube(table, dp) - sample_cube(table, dm)) / (2 * h)
    return j


def primaries_from_matrix(m):
    """xy chromaticities of the source gamut implied by src->Rec.709 M."""
    rec709_to_xyz = np.array([
        [0.4123908, 0.3575843, 0.1804808],
        [0.2126390, 0.7151687, 0.0721923],
        [0.0193308, 0.1191948, 0.9505322]])
    src_to_xyz = rec709_to_xyz @ m
    out = {}
    for i, name in enumerate("RGB"):
        xyz = src_to_xyz[:, i]
        s = xyz.sum()
        out[name] = (xyz[0] / s, xyz[1] / s)
    w = src_to_xyz @ np.ones(3)
    out["W"] = (w[0] / w.sum(), w[1] / w.sum())
    return out


def main():
    table, size, _, _ = read_cube(STD)
    tm = ToneMap(table)

    print("=" * 72)
    print("DJI's implied tone map (scene-linear -> display-linear)")
    print(f"  {'stops':>7} {'scene lin':>11} {'display lin':>12} {'IRE':>7}")
    for s in [-6, -5, -4, -3, -2, -1, 0, 1, 2, 3, 4, 5, 6, 8, 10]:
        x = 0.18 * 2.0 ** s
        y = float(tm(x))
        print(f"  {s:+7d} {x:11.5f} {y:12.6f} {oetf709(y) * 100:7.2f}")
    print(f"\n  middle grey -> {oetf709(float(tm(0.18))) * 100:.2f} IRE")
    ymax = tm.y[-1]
    i99 = int(np.argmax(tm.y >= ymax * 0.999))
    print(f"  render saturates at {tm.lx[i99]:+.2f} stops above grey")
    print(f"  sensor delivers about +10.0 stops, so DJI discards roughly "
          f"{10.0 - tm.lx[i99]:.1f} stops of highlight")

    print("\n" + "=" * 72)
    print("D-Gamut2 -> Rec.709 from the LUT Jacobian at neutral")
    mats = []
    print(f"  {'CV10':>6}  matrix rows (normalised)")
    for cv in [280, 312, 350, 400, 450, 500, 550]:
        j = jacobian_at(table, cv / 1023.0)
        m = j / j.sum(axis=1, keepdims=True)
        mats.append(m)
        print(f"  {cv:6d}  " + " | ".join(
            " ".join(f"{v:7.4f}" for v in row) for row in m))

    stack = np.array(mats)
    m = stack.mean(0)
    spread = stack.std(0).max()
    print(f"\n  spread across grey levels (max std) = {spread:.5f}"
          f"   {'CONSISTENT' if spread < 0.02 else 'INCONSISTENT'}")

    print("\n  D-Gamut2 -> Rec.709 (recovered):")
    for row in m:
        print("    [" + "  ".join(f"{v:9.5f}" for v in row) + "]")

    print("\n  reference matrices for comparison")
    print("    BT.2020 -> Rec.709:")
    for row in BT2020_TO_709:
        print("      [" + "  ".join(f"{v:9.5f}" for v in row) + "]")
    print("    D-Gamut (v1) -> Rec.709:")
    for row in DGAMUT_TO_709:
        print("      [" + "  ".join(f"{v:9.5f}" for v in row) + "]")

    print("\n  implied D-Gamut2 primaries (xy):")
    prim = primaries_from_matrix(m)
    for k in "RGBW":
        print(f"    {k}  x={prim[k][0]:+.4f}  y={prim[k][1]:+.4f}")
    print("    D-Gamut v1 for reference: R 0.7100 0.3100 | "
          "G 0.2100 0.8800 | B 0.0900 -0.0800")
    print("    BT.2020 for reference:    R 0.7080 0.2920 | "
          "G 0.1700 0.7970 | B 0.1310  0.0460")

    np.save(os.path.join(VENDOR, "dgamut2_to_rec709.npy"), m)
    np.save(os.path.join(VENDOR, "dji_tonemap.npy"),
            np.stack([tm.lx, tm.y]))
    print("\n  saved -> vendor/dgamut2_to_rec709.npy, vendor/dji_tonemap.npy")
    return m


if __name__ == "__main__":
    main()
