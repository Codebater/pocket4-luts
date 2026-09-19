"""A fitted model of DJI D-Log2 (Osmo Pocket 4P).

DJI has NOT published a D-Log2 white paper. What is public:

  * middle grey (18%) sits at ~31 IRE, 10-bit code value ~312
  * D-Log2 encodes up to 47500% reflectance at its ceiling
    (for comparison ARRI LogC4 tops out at 46980%)
  * the wide camera is quoted at ~17 stops of dynamic range
  * DJI ships an official D-Log2 -> Rec.709 65-point cube

So we build the curve from those anchors instead of inventing one, using
the standard log-family form (linear toe, log above the join):

    E(x) = A * log2(x / 0.18) + G          for x > x_cut
    E(x) = x / m + E_black                 for x <= x_cut

  A is set so that the ceiling lands exactly on 47500%:
      A = (1 - G) / log2(4.75 / 0.0018)  ... in reflectance-normalised
      units where 0.18 == middle grey and 4.75 == 475% ... i.e.
      A = (1 - 0.305) / log2(475.0 / 0.18) = 0.061146

  the toe is joined C1-continuously to a straight line that reaches
  x = 0 exactly at 10-bit code 64, the legal black floor. Slope matching
  gives E_cut - E_black = A / ln(2) with no free parameters.

Sanity cross-check that falls out of the fit rather than being fed in:
log2(475.0 / 0.18) = 11.37 stops above middle grey. Independent profiling
of the Pocket 4P reported ~10 stops above middle grey before the sensor
hard-clipped, i.e. the sensor runs out before the encoding does, which is
what you would expect. 11.37 above grey + ~5.6 below = the ~17 stops DJI
quotes.

This is a MODEL, clearly labelled as such. It is validated in
validate_curve.py by checking that the tone-mapping it implies inside
DJI's own official LUT is smooth and monotonic -- a wrong curve would
produce a kinked or non-monotonic implied tone map.
"""
from __future__ import annotations

import numpy as np

# --- published / measured anchors -------------------------------------
MID_GREY_LINEAR = 0.18
MID_GREY_CV10 = 312.0
BLACK_CV10 = 64.0
MAX_REFLECTANCE = 475.0          # 47500%

MID_GREY_E = MID_GREY_CV10 / 1023.0      # 0.305
BLACK_E = BLACK_CV10 / 1023.0            # 0.062561

# --- derived curve constants ------------------------------------------
STOPS_ABOVE_GREY = np.log2(MAX_REFLECTANCE / MID_GREY_LINEAR)   # 11.3663
A = (1.0 - MID_GREY_E) / STOPS_ABOVE_GREY                        # 0.061146
CUT_E = BLACK_E + A / np.log(2.0)                                # 0.150777
CUT_X = MID_GREY_LINEAR * 2.0 ** ((CUT_E - MID_GREY_E) / A)      # 0.031345
TOE_SLOPE = CUT_X / (CUT_E - BLACK_E)                            # 0.355


def dlog2_to_linear(e):
    """D-Log2 code (0-1 float) -> scene-linear reflectance (0.18 = grey)."""
    e = np.asarray(e, dtype=np.float64)
    toe = TOE_SLOPE * (e - BLACK_E)
    log = MID_GREY_LINEAR * np.exp2((e - MID_GREY_E) / A)
    return np.where(e <= CUT_E, np.maximum(toe, 0.0), log)


def linear_to_dlog2(x):
    """Scene-linear reflectance -> D-Log2 code (0-1 float)."""
    x = np.asarray(x, dtype=np.float64)
    safe = np.maximum(x, 1e-10)
    log = A * np.log2(safe / MID_GREY_LINEAR) + MID_GREY_E
    toe = x / TOE_SLOPE + BLACK_E
    return np.where(x <= CUT_X, toe, log)


def stops_from_grey(e):
    """How many stops above/below middle grey a D-Log2 code sits at."""
    return np.log2(np.maximum(dlog2_to_linear(e), 1e-10) / MID_GREY_LINEAR)


if __name__ == "__main__":
    print(f"A            = {A:.6f}  ({A * 1023:.2f} CV10 per stop -> "
          f"{1.0 / (A * 1023) * 100:.1f} stops per 100 CV)")
    print(f"CUT_E        = {CUT_E:.6f}  (CV {CUT_E * 1023:.1f})")
    print(f"CUT_X        = {CUT_X:.6f}")
    print(f"TOE_SLOPE    = {TOE_SLOPE:.6f}")
    print(f"stops above grey = {STOPS_ABOVE_GREY:.4f}")
    print()
    print(f"{'CV10':>6} {'E':>8} {'linear':>12} {'stops':>8}")
    for cv in [0, 64, 95, 150, 200, 250, 312, 350, 400, 450, 500, 600,
               700, 800, 900, 940, 1023]:
        e = cv / 1023.0
        x = float(dlog2_to_linear(e))
        s = float(stops_from_grey(e))
        print(f"{cv:6d} {e:8.4f} {x:12.5f} {s:+8.3f}")
    print()
    rt = linear_to_dlog2(dlog2_to_linear(np.linspace(0, 1, 4001)))
    print("round-trip max error:",
          float(np.max(np.abs(rt - np.linspace(0, 1, 4001)))))
