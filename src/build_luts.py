"""Build the Pocket 4P D-Log2 LUT pack.

Every LUT shares one base transform (see looks.py for why it is built the
way it is) and then applies its own display-referred look on top.
"""
from __future__ import annotations

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import looks as L  # noqa: E402
from dlog2 import dlog2_to_linear, linear_to_dlog2  # noqa: E402
from lutlib import identity_grid, read_cube, sample_cube, write_cube  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
VENDOR = os.path.join(ROOT, "vendor")
OUT = os.path.join(ROOT, "luts")
DJI_STD = os.path.join(
    VENDOR, "DJI_OSMO_Pocket_4P_D-Log2_to_Rec709_V1.0_size65.cube")

PACK = "POCKET 4P"
VERSION = "v1.0"

_dji = None


def dji_table():
    global _dji
    if _dji is None:
        _dji, _, _, _ = read_cube(DJI_STD)
    return _dji


def _render(e, recovery, knee, ceiling):
    x = dlog2_to_linear(e)
    x = L.highlight_compress(x, knee_stops=knee, ceiling_stops=ceiling,
                             amount=recovery)
    return sample_cube(dji_table(), np.clip(linear_to_dlog2(x), 0.0, 1.0))


def base_render(e, recovery=1.0, knee=2.0, ceiling=6.9,
                shoulder=0.55, shoulder_start=0.80):
    """D-Log2 code -> display Rec.709, with the highlights kept.

    recovery=0 reproduces DJI's official render exactly. The closing
    shoulder is normalised against whatever the very top of the D-Log2
    range renders to, so peak white lands on 1.0 instead of somewhere
    dull below it.
    """
    v = _render(e, recovery, knee, ceiling)
    top = float(_render(np.ones((1, 3)), recovery, knee, ceiling).max())
    return L.soft_shoulder(v, shoulder, shoulder_start, white_at=top)


# --------------------------------------------------------------- looks
def look_neutral(v):
    """Reference render: DJI's colour and contrast, highlights intact.

    Deliberately a pass-through -- all the work already happened in the
    base. Anything added here would be a look, not a reference.
    """
    return v


def look_flat(v):
    """Low-contrast grading base -- room to work, not a finished image."""
    v = L.contrast(v, -0.42)
    v = L.saturation(v, 0.88)
    v = L.toe(v, lift=0.045)
    return v


def look_natural(v):
    """Daily driver: true-to-life, skin nudged warm, greens kept honest.

    Tuned against measure_looks.py on real footage: a look called Natural
    has no business tinting neutral walls, so the warmth is small and the
    lifting happens on skin specifically rather than globally.
    """
    v = L.contrast(v, 0.10)
    v = L.temperature(v, 0.020, -0.008)
    v = L.hue_zone(v, 30, 45, sat_mul=1.02, hue_rot_deg=3.0)     # skin
    v = L.hue_zone(v, 110, 55, sat_mul=0.90, hue_rot_deg=-8.0)     # foliage
    v = L.vibrance(v, 0.10)
    v = L.soft_shoulder(v, 0.6, 0.80)
    return v


def look_print_film(v):
    """Print-stock feel: dense blacks, warm highlights, cool shadow toe."""
    v = L.contrast(v, 0.26)
    v = L.split_tone(v, shadow_rgb=(-0.008, 0.001, 0.018),
                     highlight_rgb=(0.018, 0.007, -0.014), balance=0.45)
    v = L.channel_curve(
        v,
        r_pts=[(0, 0.010), (0.25, 0.245), (0.75, 0.790), (1, 1.0)],
        g_pts=[(0, 0.008), (0.25, 0.242), (0.75, 0.775), (1, 0.997)],
        b_pts=[(0, 0.026), (0.25, 0.252), (0.75, 0.760), (1, 0.985)])
    v = L.hue_zone(v, 30, 45, sat_mul=1.00, hue_rot_deg=4.0)
    v = L.saturation(v, 1.00)
    v = L.soft_shoulder(v, 0.75, 0.76)
    return v


def look_teal_amber(v):
    """The commercial standard: amber skin against teal everything-else."""
    v = L.contrast(v, 0.22)
    v = L.split_tone(v, shadow_rgb=(-0.022, 0.003, 0.034),
                     highlight_rgb=(0.026, 0.010, -0.022), balance=0.48,
                     strength=1.05)
    v = L.hue_zone(v, 30, 40, sat_mul=1.08, hue_rot_deg=6.0)     # skin amber
    v = L.hue_zone(v, 200, 60, sat_mul=1.22, hue_rot_deg=-6.0)     # teal
    v = L.vibrance(v, 0.08)
    v = L.soft_shoulder(v, 0.7, 0.78)
    return v


def look_bleach(v):
    """Bleach bypass: silver retained, colour pulled, contrast up."""
    v = L.contrast(v, 0.46)
    v = L.saturation(v, 0.42)
    v = L.split_tone(v, shadow_rgb=(0.004, 0.006, 0.014),
                     highlight_rgb=(0.014, 0.014, 0.010), balance=0.5)
    v = L.toe(v, crush=0.012)
    v = L.soft_shoulder(v, 0.9, 0.72)
    return v


def look_night_neon(v):
    """For interiors and after dark: shadows kept open, highlights held,
    magenta/cyan separation instead of a wash of orange."""
    v = L.contrast(v, 0.14)
    v = L.toe(v, lift=0.020)
    v = L.split_tone(v, shadow_rgb=(0.012, -0.008, 0.034),
                     highlight_rgb=(0.020, -0.004, 0.014), balance=0.42,
                     strength=1.2)
    v = L.hue_zone(v, 300, 60, sat_mul=1.25)                      # magenta
    v = L.hue_zone(v, 190, 55, sat_mul=1.20)                      # cyan
    v = L.hue_zone(v, 30, 40, sat_mul=1.05, hue_rot_deg=3.0)     # skin
    v = L.soft_shoulder(v, 1.0, 0.70)
    return v


def look_golden(v):
    """Golden hour, or a convincing impression of it.

    The first pass tinted neutral walls 16% and pushed skin to 0.49
    saturation, which reads as sunburn rather than sunlight. Halved.
    """
    v = L.contrast(v, 0.16)
    v = L.temperature(v, 0.072, -0.020)
    v = L.split_tone(v, shadow_rgb=(0.004, -0.001, 0.011),
                     highlight_rgb=(0.024, 0.010, -0.016), balance=0.44)
    v = L.hue_zone(v, 40, 50, sat_mul=1.05)
    v = L.vibrance(v, 0.07)
    v = L.soft_shoulder(v, 0.8, 0.76)
    return v


def look_nordic(v):
    """Cool, muted, overcast. Greens desaturated toward slate."""
    v = L.contrast(v, 0.20)
    v = L.temperature(v, -0.13, 0.03)
    v = L.hue_zone(v, 110, 70, sat_mul=0.55, hue_rot_deg=-12.0)
    # cooling everything drags skin toward magenta; rotate it back so the
    # look reads cold without the faces turning pink
    v = L.hue_zone(v, 22, 42, sat_mul=1.08, hue_rot_deg=5.0)
    v = L.saturation(v, 0.86)
    v = L.split_tone(v, shadow_rgb=(-0.010, 0.000, 0.022),
                     highlight_rgb=(-0.006, 0.002, 0.014), balance=0.5)
    v = L.soft_shoulder(v, 0.7, 0.78)
    return v


def look_mono(v):
    """Black and white with an orange-filter response and a warm print tone."""
    v = L.contrast(v, 0.30)
    v = L.monochrome(v, weights=(0.42, 0.46, 0.12), tone=(1.010, 1.0, 0.978))
    v = L.toe(v, crush=0.010)
    v = L.soft_shoulder(v, 0.85, 0.74)
    return v


def look_retro_fade(v):
    """Faded emulsion: milk in the blacks, cyan shadows, soft highlights."""
    v = L.contrast(v, 0.06)
    v = L.toe(v, lift=0.070)
    v = L.split_tone(v, shadow_rgb=(-0.010, 0.004, 0.022),
                     highlight_rgb=(0.022, 0.011, -0.008), balance=0.5,
                     strength=0.9)
    v = L.saturation(v, 0.82)
    v = L.hue_zone(v, 30, 45, sat_mul=1.08)
    v = L.channel_curve(
        v,
        r_pts=[(0, 0.060), (0.5, 0.520), (1, 0.975)],
        g_pts=[(0, 0.055), (0.5, 0.505), (1, 0.962)],
        b_pts=[(0, 0.085), (0.5, 0.497), (1, 0.950)])
    v = L.soft_shoulder(v, 0.9, 0.70)
    return v


def look_punch(v):
    """Vertical/social: reads at thumbnail size and on a phone in sunlight."""
    v = L.contrast(v, 0.38)
    v = L.vibrance(v, 0.13)
    v = L.saturation(v, 0.96)
    v = L.hue_zone(v, 30, 40, sat_mul=1.05, hue_rot_deg=3.0)
    v = L.hue_zone(v, 110, 55, sat_mul=0.88, hue_rot_deg=-8.0)
    v = L.toe(v, crush=0.008)
    v = L.soft_shoulder(v, 0.9, 0.74)
    return v


LOOKS = [
    ("01", "Neutral",   look_neutral,    1.0,
     "Reference. DJI colour science with the clipped highlights recovered."),
    ("02", "FlatBase",  look_flat,       1.0,
     "Low-contrast base to grade on top of. Not a finished look."),
    ("03", "Natural",   look_natural,    1.0,
     "Everyday. True-to-life with warmer skin and calmer greens."),
    ("04", "PrintFilm", look_print_film, 1.0,
     "Photochemical print feel: dense blacks, warm highlights."),
    ("05", "TealAmber", look_teal_amber, 1.0,
     "Commercial teal and orange, skin protected."),
    ("06", "Bleach",    look_bleach,     1.0,
     "Bleach bypass. High contrast, most of the colour pulled out."),
    ("07", "NightNeon", look_night_neon, 1.0,
     "Interiors and night. Open shadows, magenta/cyan separation."),
    ("08", "Golden",    look_golden,     1.0,
     "Warm golden-hour bias with amber highlights."),
    ("09", "Nordic",    look_nordic,     1.0,
     "Cold and muted. Overcast, slate greens."),
    ("10", "Mono",      look_mono,       1.0,
     "Black and white, orange-filter response, warm print tone."),
    ("11", "RetroFade", look_retro_fade, 1.0,
     "Faded stock. Lifted milky blacks, cyan shadows."),
    ("12", "Punch",     look_punch,      1.0,
     "High contrast and saturation for social and vertical."),
]


def build(size=33, outdir=None, verbose=True):
    outdir = outdir or OUT
    os.makedirs(outdir, exist_ok=True)
    grid = identity_grid(size)
    made = []
    for num, name, fn, recovery, desc in LOOKS:
        t0 = time.time()
        v = base_render(grid, recovery=recovery)
        v = fn(v)
        v = np.clip(v, 0.0, 1.0)
        fname = f"P4P_{num}_{name}_size{size}.cube"
        path = os.path.join(outdir, fname)
        write_cube(
            path, v, size,
            title=f"{PACK} {name} {VERSION}",
            comments=[
                f"{PACK} D-Log2 LUT pack {VERSION} - {name}",
                desc,
                "Input:  DJI Osmo Pocket 4P D-Log2 / D-Gamut2, full range",
                "Output: Rec.709 / gamma 2.4 display",
                "Built on DJI's official D-Log2 to Rec.709 colorimetry with a",
                "scene-linear highlight shoulder so nothing clips at +7 stops.",
            ])
        made.append(fname)
        if verbose:
            print(f"  {fname:42s} {time.time() - t0:5.1f}s")
    return made


if __name__ == "__main__":
    sizes = [int(a) for a in sys.argv[1:]] or [33, 65]
    for s in sizes:
        print(f"\nbuilding {s}-point LUTs -> {OUT}")
        build(s)
    print("\ndone")
