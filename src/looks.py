"""Look engine: the grading operators the LUT pack is built from.

Design note on where the maths happens.

The base transform is deliberately NOT a from-scratch gamut pipeline.
DJI's official cube already contains their full colorimetry for this
sensor -- skin, hue, the lot -- and that part of their LUT is good. What
is bad is the tone render: measured off their own file, it saturates at
+7.06 stops above middle grey while the sensor delivers about +10, so
DJI bin roughly 3 stops of highlight into flat white.

So the base is:

    E  ->  scene-linear (fitted D-Log2 curve)
       ->  per-channel highlight compression, nothing above the knee clips
       ->  back to D-Log2 code
       ->  DJI's official cube            <- their colorimetry, untouched
       ->  contrast restored in display

which keeps everything DJI got right, removes the clip, and invents no
colour science. Creative looks then run on the display-referred result,
which is what look LUTs and print emulations have always done.
"""
from __future__ import annotations

import numpy as np

GREY_DISPLAY = 0.4135      # where DJI's render puts 18% grey (measured)


# ---------------------------------------------------------------- utils
def _l(x):
    return np.asarray(x, dtype=np.float64)


def eotf709(v):
    """Rec.709 EOTF, extended above 1.0 rather than clamped.

    The look chain has to stay over-range until the final shoulder. Clamping
    here is what made contrast() flatten every highlight above +4 stops in
    the first build.
    """
    v = np.maximum(_l(v), 0.0)
    return np.where(v < 0.081, v / 4.5,
                    np.power((v + 0.099) / 1.099, 1.0 / 0.45))


def oetf709(lin):
    lin = np.maximum(_l(lin), 0.0)
    return np.where(lin < 0.018, lin * 4.5,
                    1.099 * np.power(np.maximum(lin, 1e-12), 0.45) - 0.099)


LUMA = np.array([0.2126, 0.7152, 0.0722])


def luma(rgb):
    return (_l(rgb) * LUMA).sum(-1, keepdims=True)


# ------------------------------------------------- scene-linear shaping
def highlight_compress(x, knee_stops=2.0, ceiling_stops=6.9, amount=1.0):
    """Per-channel soft shoulder in scene-linear, expressed in stops.

    Below `knee_stops` nothing is touched at all, so mid-tones and skin
    come through DJI's render bit-identical. Above it an exponential
    shoulder asymptotes to `ceiling_stops`, so no input value -- however
    bright -- can ever reach DJI's clip point. Slope is 1 at the knee, so
    there is no visible kink.
    """
    if amount <= 0.0:
        return x
    x = np.maximum(_l(x), 1e-10)
    s = np.log2(x / 0.18)
    span = (ceiling_stops - knee_stops) / max(amount, 1e-6)
    over = s - knee_stops
    shoulder = knee_stops + span * (1.0 - np.exp(-np.maximum(over, 0.0) / span))
    s_new = np.where(s <= knee_stops, s, shoulder)
    return 0.18 * np.exp2(s_new)


# -------------------------------------------------- display-space tools
def contrast(rgb, amount, pivot=GREY_DISPLAY):
    """S-curve contrast about a pivot, applied in display-linear so it
    does not tear the shadows the way a code-value curve does."""
    if amount == 0.0:
        return rgb
    lin = eotf709(rgb)
    p = float(eotf709(np.array([pivot]))[0])
    out = p * np.power(np.maximum(lin / p, 1e-10), 1.0 + amount)
    return oetf709(out)


def soft_shoulder(rgb, strength=0.0, start=0.75, white_at=None):
    """Roll-off near display white, asymptotic to 1.0.

    Anything at or above `start` is compressed; the curve approaches 1.0
    but never exceeds it, so over-range values coming out of contrast()
    land back in gamut with their separation intact instead of clipping.

    `white_at` normalises the curve so that this input value maps to
    exactly 1.0. The base render uses it so peak white is real white --
    without it the first build topped out at 0.885 and read washed.
    """
    if strength <= 0.0:
        return rgb
    v = _l(rgb)
    span = 1.0 - start
    k = span / max(strength, 1e-6)

    def roll(t):
        return start + span * (1.0 - np.exp(-np.maximum(t - start, 0.0) / k))

    rolled = roll(v)
    if white_at is not None and white_at > start:
        peak = float(roll(np.array([float(white_at)]))[0])
        rolled = start + (rolled - start) * (span / max(peak - start, 1e-9))
    return np.where(v <= start, v, rolled)


def toe(rgb, lift=0.0, crush=0.0):
    """lift raises the black floor (faded look); crush deepens it."""
    v = _l(rgb)
    if crush:
        v = np.maximum(v - crush, 0.0) / max(1.0 - crush, 1e-6)
    if lift:
        v = lift + v * (1.0 - lift)
    return v


def saturation(rgb, amount):
    if amount == 1.0:
        return rgb
    v = _l(rgb)
    return luma(v) + (v - luma(v)) * amount


def vibrance(rgb, amount):
    """Saturation weighted by how unsaturated a pixel already is, so skin
    and other low-chroma areas move far less than a flat sat boost."""
    if amount == 0.0:
        return rgb
    v = _l(rgb)
    y = luma(v)
    chroma = v - y
    mx = np.maximum(v.max(-1, keepdims=True), 1e-6)
    mn = v.min(-1, keepdims=True)
    sat = (mx - mn) / mx
    w = np.clip(1.0 - sat, 0.0, 1.0) ** 1.5
    return y + chroma * (1.0 + amount * w)


def temperature(rgb, kelvin_shift=0.0, tint_shift=0.0):
    """Approximate warm/cool and green/magenta trim, in display-linear."""
    if kelvin_shift == 0.0 and tint_shift == 0.0:
        return rgb
    lin = eotf709(rgb)
    k = kelvin_shift
    gain = np.array([1.0 + 0.55 * k, 1.0 + 0.06 * k - 0.30 * tint_shift,
                     1.0 - 0.50 * k + 0.22 * tint_shift])
    lin = lin * gain
    # renormalise so overall exposure does not drift
    lin = lin / max(float((gain * LUMA).sum()), 1e-6)
    return oetf709(lin)


def lift_gamma_gain(rgb, lift=(0, 0, 0), gamma=(1, 1, 1), gain=(1, 1, 1)):
    v = _l(rgb)
    lift = np.array(lift, dtype=np.float64)
    gamma = np.array(gamma, dtype=np.float64)
    gain = np.array(gain, dtype=np.float64)
    v = v * gain + lift * (1.0 - v)
    v = np.power(np.maximum(v, 0.0), 1.0 / gamma)
    return v


def split_tone(rgb, shadow_rgb=(0, 0, 0), highlight_rgb=(0, 0, 0),
               balance=0.5, strength=1.0):
    """Push colour into shadows and highlights independently."""
    if strength == 0.0:
        return rgb
    v = _l(rgb)
    y = luma(v)
    w_hi = np.clip((y - balance) / max(1.0 - balance, 1e-6), 0.0, 1.0) ** 1.2
    w_lo = np.clip((balance - y) / max(balance, 1e-6), 0.0, 1.0) ** 1.2
    s = np.array(shadow_rgb, dtype=np.float64)
    h = np.array(highlight_rgb, dtype=np.float64)
    return v + strength * (w_lo * s + w_hi * h)


def hue_zone(rgb, center_deg, width_deg, sat_mul=1.0, hue_rot_deg=0.0,
             lum_mul=1.0):
    """HSL-style qualifier: nudge one hue family only.

    Used to keep foliage from going radioactive and to steer skin without
    dragging the rest of the frame with it.
    """
    v = np.maximum(_l(rgb), 0.0)
    # hue is scale-invariant, so detect it on a copy normalised into 0-1
    # while the operators below still act on the over-range original
    vh = v / np.maximum(v.max(-1, keepdims=True), 1.0)
    mx = vh.max(-1)
    mn = vh.min(-1)
    d = mx - mn
    r, g, b = vh[..., 0], vh[..., 1], vh[..., 2]
    h = np.zeros_like(mx)
    nz = d > 1e-9
    with np.errstate(invalid="ignore", divide="ignore"):
        hr = np.where(mx == r, ((g - b) / np.where(nz, d, 1)) % 6.0, 0.0)
        hg = np.where(mx == g, (b - r) / np.where(nz, d, 1) + 2.0, 0.0)
        hb = np.where(mx == b, (r - g) / np.where(nz, d, 1) + 4.0, 0.0)
    h = np.where(mx == r, hr, np.where(mx == g, hg, hb)) * 60.0
    h = np.where(nz, h, 0.0)

    dist = np.abs(((h - center_deg + 180.0) % 360.0) - 180.0)
    w = np.clip(1.0 - dist / max(width_deg, 1e-6), 0.0, 1.0)
    w = (w ** 2 * (3 - 2 * w))[..., None]          # smoothstep
    w = w * (d > 1e-6)[..., None]

    y = luma(v)
    out = v
    if sat_mul != 1.0:
        out = y + (out - y) * (1.0 + (sat_mul - 1.0) * w[..., 0:1])
    if lum_mul != 1.0:
        out = out * (1.0 + (lum_mul - 1.0) * w)
    if hue_rot_deg != 0.0:
        # negated so positive = toward a higher hue angle (red -> orange ->
        # yellow), matching how the parameter reads. The raw chroma-plane
        # rotation runs the other way and silently sent Nordic's skin to
        # magenta when it was asked for warmth.
        a = np.deg2rad(-hue_rot_deg) * w[..., 0]
        cos, sin = np.cos(a), np.sin(a)
        c1 = (2 * out[..., 0] - out[..., 1] - out[..., 2]) / 3.0
        c2 = (out[..., 2] - out[..., 1]) / np.sqrt(3.0)
        yy = luma(out)[..., 0]
        n1 = c1 * cos - c2 * sin
        n2 = c1 * sin + c2 * cos
        out = np.stack([
            yy + n1,
            yy - 0.5 * n1 - np.sqrt(3.0) / 2.0 * n2,
            yy - 0.5 * n1 + np.sqrt(3.0) / 2.0 * n2], axis=-1)
    return out


def channel_curve(rgb, r_pts=None, g_pts=None, b_pts=None):
    """Per-channel curve from control points [(x, y), ...] in 0-1."""
    v = _l(rgb).copy()
    for i, pts in enumerate((r_pts, g_pts, b_pts)):
        if not pts:
            continue
        xs = np.array([p[0] for p in pts], dtype=np.float64)
        ys = np.array([p[1] for p in pts], dtype=np.float64)
        ch = v[..., i]
        over = np.maximum(ch - 1.0, 0.0)       # keep over-range headroom
        v[..., i] = np.interp(np.clip(ch, 0.0, 1.0), xs, ys) + over
    return v


def monochrome(rgb, weights=(0.2126, 0.7152, 0.0722), tone=(1.0, 1.0, 1.0)):
    v = _l(rgb)
    y = (v * np.array(weights)).sum(-1, keepdims=True)
    return y * np.array(tone)
