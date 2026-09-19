"""Check the built pack actually does what it claims.

The headline claim is highlight recovery, so that gets measured against
DJI's official file rather than asserted.
"""
from __future__ import annotations

import glob
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from dlog2 import dlog2_to_linear  # noqa: E402
from lutlib import read_cube, sample_cube  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
DJI = os.path.join(ROOT, "vendor",
                   "DJI_OSMO_Pocket_4P_D-Log2_to_Rec709_V1.0_size65.cube")


def neutral(table, e):
    return sample_cube(table, np.stack([e, e, e], -1)).mean(-1)


def main():
    dji, _, _, _ = read_cube(DJI)
    size = int(sys.argv[1]) if len(sys.argv) > 1 else 33
    files = sorted(glob.glob(os.path.join(ROOT, "luts", f"*_size{size}.cube")))
    if not files:
        print(f"no size{size} LUTs built yet")
        return 1
    print(f"validating {len(files)} LUTs at size {size}\n")

    print("=" * 74)
    print("HIGHLIGHT RECOVERY  (does the LUT still resolve detail up top?)")
    e = np.linspace(0.0, 1.0, 4096)
    lin = dlog2_to_linear(e)
    stops = np.log2(np.maximum(lin, 1e-10) / 0.18)

    def cv_per_stop(table, lo, hi):
        """10-bit output code values spent per stop between lo and hi stops.
        Under ~2 CV/stop the highlight is perceptually gone."""
        n = neutral(table, e)
        a = float(np.interp(lo, stops, n))
        b = float(np.interp(hi, stops, n))
        return (b - a) * 1023.0 / (hi - lo)

    def white_at(table):
        return float(neutral(table, np.array([1.0]))[0])

    print(f"  DJI official spends {cv_per_stop(dji, 4, 8):5.2f} CV per stop "
          f"between +4 and +8 stops")
    print()
    # Tolerance is one 10-bit code value. DJI's own cube has 98 negative
    # steps on its neutral axis (worst -0.17 CV10) around the black floor,
    # and we inherit them; anything under a code value cannot be seen or
    # even represented in a 10-bit deliverable, so it is reported rather
    # than treated as a defect.
    tol_cv = 1.0
    print(f"  {'LUT':34s} {'+4..+8':>8} {'+6..+10':>8} {'white':>7} "
          f"{'worst dip':>10} {'range':>13}")
    fails = []
    for f in files + [DJI]:
        t, _, _, _ = read_cube(f)
        n = neutral(t, e)
        dip_cv = float(np.diff(n).min()) * 1023.0
        mono = dip_cv >= -tol_cv
        mn, mx = t.min(), t.max()
        finite = bool(np.all(np.isfinite(t)))
        ok = mono and finite and mn >= -1e-6 and mx <= 1.0 + 1e-6
        if not ok and f != DJI:
            fails.append(os.path.basename(f))
        tag = ("-- DJI official (reference) --" if f == DJI
               else os.path.basename(f))
        flag = "" if ok or f == DJI else "  FAIL"
        print(f"  {tag:34s} {cv_per_stop(t, 4, 8):8.2f} "
              f"{cv_per_stop(t, 6, 10):8.2f} {white_at(t):7.3f} "
              f"{dip_cv:+9.3f}CV {mn:6.3f}..{mx:5.3f}{flag}")

    print("\n" + "=" * 74)
    print("MID-TONE FIDELITY  (below the knee we must match DJI exactly)")
    neu = [f for f in files if "Neutral" in f][0]
    t, _, _, _ = read_cube(neu)
    print(f"  {'stops':>6} {'DJI':>9} {'Neutral':>9} {'delta':>9}")
    worst = 0.0
    for s in [-4, -3, -2, -1, 0, 1, 1.5, 2, 3, 4, 6, 8]:
        x = 0.18 * 2.0 ** s
        code = float(np.interp(x, lin, e))
        a = float(neutral(dji, np.array([code]))[0])
        b = float(neutral(t, np.array([code]))[0])
        if s <= 1.5:
            worst = max(worst, abs(a - b))
        print(f"  {s:+6.1f} {a:9.5f} {b:9.5f} {b - a:+9.5f}")
    print(f"\n  max deviation below the knee: {worst:.5f} "
          f"({worst * 1023:.1f} CV10)  "
          f"{'PASS' if worst < 0.02 else 'FAIL'}")

    print("\n" + "=" * 74)
    print("CLIPPED PIXEL COUNT on a synthetic 17-stop ramp")
    ramp = np.linspace(0.0, 1.0, 100000)
    for f in [neu, DJI]:
        t, _, _, _ = read_cube(f)
        n = neutral(t, ramp)
        pct = 100.0 * np.mean(n >= 0.999)
        print(f"  {os.path.basename(f):46s} {pct:5.2f}% at full white")

    print()
    if fails:
        print("FAILURES:", fails)
        return 1
    print(f"all LUTs finite, in range, and monotonic within {tol_cv:.0f} code value")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
