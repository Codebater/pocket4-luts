# D-Log 2 on the Osmo Pocket 4P — what's documented, what isn't, what we did

Written so that every number in this pack can be traced to either a
published source or a measurement, and so it's obvious which is which.

---

## 1. What DJI actually publishes

| Fact | Value | Source |
|---|---|---|
| Wide sensor | 1" CMOS with LOFIC | DJI / CineD launch coverage |
| Dynamic range | ~17 stops claimed (wide) | DJI |
| Highlight latitude | up to 11.3 EV | CineD |
| D-Log 2 | 10-bit log profile | DJI |
| Encoding ceiling | **47500% reflectance** (LogC4 = 46980%) | published comparisons |
| Middle grey | ~**31 IRE**, 10-bit **CV ≈ 312** | DJI whitepapers via colourists |
| Gamut | **D-Gamut 2** — shares D-Gamut's blue primary; red and green moved out to fully cover BT.2020 and to sit on the ACES AP0 boundary | published analysis |
| LogC4 relation | "a simple hue transform adapts D-Log 2 to the ARRI ALEXA 35 LogC4 workflow" | DJI |
| Official LUTs | D-Log2 → Rec.709, 33 and 65 point, standard + vivid | DJI download centre |
| Official ACES path | DCTL `Dlog2_DGamut2_to_ACES_AP0_cat02.dctl` → AP0, then ACEScct | DJI *D-Log2 Recommended ACES Workflow* PDF |

**There is no D-Log 2 white paper.** DJI published one for D-Log/D-Gamut
(Zenmuse X7, then X9) but not for D-Log 2. The ACES workflow PDF describes
*how to use* their DCTL without printing the transform, and the DCTL is
not on the public download page.

For reference, the original **D-Log** curve *is* fully published:

```
encode:  in <= 0.0078 : out = 6.025 * in + 0.0929
         in >  0.0078 : out = log10(in * 0.9892 + 0.0108) * 0.256663 + 0.584555
decode:  in <= 0.14   : out = (in - 0.0929) / 6.025
         in >  0.14   : out = (10^(3.89616*in - 2.27752) - 0.0108) / 0.9892
```

with 10-bit code values 0% → 95, 18% → 408, 90% → 586, and **D-Gamut**
primaries R (0.71, 0.31), G (0.21, 0.88), B (0.09, −0.08), white D65.

D-Log 2 is a **different curve and a different gamut**. None of the above
applies to it, beyond the shared blue primary.

---

## 2. The D-Log 2 curve we fitted

Since the real one isn't public, `src/dlog2.py` builds one from the
published anchors using the standard log family (linear toe, log above a
join):

```
E(x) = A * log2(x / 0.18) + 0.305       above the join
E(x) = x / m + E_black                  below it
```

* `A` is fixed by making the ceiling land exactly on 47500%:
  `A = (1 − 0.305) / log2(475.0 / 0.18) = 0.061146`
  → **62.56 code values per stop**
* the toe is joined C¹-continuously to a line reaching `x = 0` at 10-bit
  code 64 (legal black). Slope matching gives `E_cut − E_black = A / ln2`
  with **no free parameters** — nothing was tuned by eye.

### Why we believe it

Three independent checks the fit was never given:

1. `log2(475.0 / 0.18) = 11.37` stops above middle grey. Independent
   profiling of the Pocket 4P reported **~10 stops above middle grey
   before the sensor hard-clipped** — sensor runs out before the encoding
   does, exactly as expected.
2. 11.37 above grey + ~5.6 below = **~17 stops**, matching DJI's claim,
   and explaining why middle grey sits so unusually low at 31 IRE.
3. The model puts **CV 940 at +10.04 stops** — and CV 940 is precisely
   where DJI's own official LUT stops responding (measured below). Two
   completely separate routes to the same number.

**This is a model, not DJI's math.** It is accurate enough to build LUTs
on; it is not a substitute for a white paper.

---

## 3. What we measured in DJI's official LUT

From `DJI OSMO Pocket 4P D-Log2 to Rec.709 V1.0 size65.cube`, sampled
directly (`src/analyze_dji.py`, `src/fit_gamut.py`):

**Their tone render**, recovered off the neutral axis:

| stops above grey | display-linear | IRE |
|---|---|---|
| −4 | 0.0146 | 6.6 |
| −2 | 0.0454 | 17.4 |
| **0** | **0.1835** | **41.4** |
| +2 | 0.4619 | 67.7 |
| +4 | 0.7607 | 87.3 |
| +6 | 0.9292 | 96.4 |
| +8 | 0.9868 | 99.4 |
| +10 | 0.9997 | 100.0 |

Two findings drive this whole pack:

1. **DJI's render saturates at about +7.1 stops above middle grey.** The
   sensor delivers roughly +10. On a synthetic ramp, **13.0% of the
   D-Log2 code range maps to pure white.** DJI ship a 17-stop camera and
   a display LUT that throws away roughly the top 3 stops.
2. **The vivid LUT hard-clips saturated colour.** Measured: log red
   → `(1.000, 0.000, 0.043)`, foliage → `(0.001, 0.749, 0.287)`. Fine as
   a look, unusable as a grading base.

Their mid-tones and hue rendering, by contrast, are good — which is why
this pack keeps them.

---

## 4. D-Gamut 2 — why we don't ship a matrix

We tried two routes to recover the D-Gamut2 → Rec.709 matrix from the
official LUT:

* **Global least-squares** of a per-channel-tone-map model: failed badly,
  RMS 0.119 (≈122 CV10). DJI's render is not a per-channel tone map of a
  matrixed linear signal — there's luminance-dependent saturation and
  hue work in there.
* **Jacobian at neutral.** At a neutral point the chain rule makes the
  Jacobian equal `M` scaled row-uniformly, so normalising each row by its
  own sum should return `M` regardless of the tone map's shape. But the
  answer **drifts with luminance** (max std 0.218 across grey levels),
  because DJI ramp saturation with brightness — so the Jacobian is
  `Sat(L) · M`, not `k · M`.

We even tested a sharp falsification: AP0's red–green edge is exactly the
line `x + y = 1`, so if D-Gamut2's R and G really sit on the AP0
boundary, both should satisfy that. Across grey levels the recovered
primaries scattered from `x+y = 0.91` to `1.06` — too noisy on a 65³ LUT
to pin anything down.

Averaged, the recovered primaries land plausibly (R ≈ 0.71/0.30,
G ≈ 0.17/0.82, B ≈ 0.085/−0.065, i.e. blue near D-Gamut v1's as DJI
state) — but "plausible" isn't good enough to ship as colour science.

**So the pack uses no invented matrix.** See below.

---

## 5. The architecture we chose

Because DJI's *colorimetry* is good and their *tone render* is not, the
base transform keeps the first and replaces the second:

```
D-Log2 code
   → scene-linear                 (fitted curve, section 2)
   → per-channel highlight shoulder in stops   ← the fix
   → back to D-Log2 code
   → DJI's official 65³ cube      ← their colorimetry, untouched
   → normalised display shoulder  (peak white lands on 1.0)
```

The shoulder is exponential, asymptotic to a ceiling **below DJI's clip
point**, with slope exactly 1 at the knee — so nothing kinks, and no
input value however bright can ever reach the clip. Below the knee
(+2 stops) it is a mathematical no-op, which is why measured mid-tone
deviation from DJI is **1.2 CV10 at worst**: skin and mid-tones come
through bit-for-bit as DJI intended.

Result, measured (`src/validate.py`):

| | +4→+8 stops | +6→+10 stops | pure white |
|---|---|---|---|
| DJI official | 30.9 CV/stop | 9.1 CV/stop | **13.0%** of range |
| P4P Neutral | 29.6 CV/stop | **11.4 CV/stop** | **0.00%** |

Same mid-tone contrast, more highlight separation up top, nothing clipped.

Creative looks then run display-referred, which is what look LUTs and
print emulations have always done.

---

## 6. Validation on real footage

Source: `DJI_20260821153413_0004_D.MP4` — 3840×2160, HEVC Main 10,
yuv420p10le, 120 Mbps, 59.94p, D-Log 2, interior with a bright doorway.

**Range.** The file is tagged `color_range=tv` and the raw 10-bit luma
measures **min 112, max 817 — nothing below 64 or above 940**. So it is
genuinely video-legal encoded, and the video-legal expansion maps
`64 → 0.0` and `940 → 1.0`, landing exactly on the LUT domain with no
dead space at either end. Full-range would leave the bottom 6% and top 8%
of the LUT permanently unused. The standard expanded path is therefore
correct, which is also the ffmpeg and Resolve default — and it is why DJI
document no special range step. Our LUTs compose DJI's, so they are
domain-compatible with it by construction either way.

**Highlight separation by stop band**, output code values spread across
each band (p1→p99), on the doorway crop:

| band | pixels | DJI | ours | gain |
|---|---|---|---|---|
| +3…+5 | 6790 | 146.0 CV | 141.2 CV | 0.97× |
| +5…+6 | 8326 | 32.9 CV | 29.8 CV | 0.90× |
| +6…+7 | 14820 | 18.5 CV | 21.1 CV | **1.14×** |
| +7…+8 | 22849 | 8.3 CV | 10.1 CV | **1.22×** |

The scene peaks at +8.10 stops, so **neither LUT hard-clipped here** —
DJI compress rather than clip at this level. The pack buys 14–22% more
separation in the top two stops and pays 3–10% between +5 and +6. That is
a redistribution, not new information, and it should be described that
way. The 13.0% → 1.7% clipping figure is a full-range ramp measurement
and only translates to a visible win on scenes that genuinely exceed
+7 stops.

**Look tuning.** `src/measure_looks.py` measures how far each look tints
a surface that is neutral in the log source, plus skin hue/saturation/
luma. The first pass failed on its own terms: Golden tinted neutrals
**16.4%** and pushed skin to **0.49** saturation (sunburn, not sunlight),
PrintFilm **11.4%**, and "Natural" — a look whose whole job is not to
editorialise — **6.5%**. After tuning: Golden 9.3%, PrintFilm 7.2%,
Natural 4.7%, and every look's skin hue lands in **18–23°** against the
Neutral reference of 19.8°.

That pass also exposed a sign bug: `hue_rot_deg` rotated the *opposite*
way to its name, so Nordic's attempt to keep skin warm under a cold grade
drove it to **11.4°** (magenta) instead. The convention is now negated
inside `hue_zone` and every call site flipped to match; Nordic's skin
sits at **19.0°**.

---

### One bug worth recording

The first build clipped every look's highlights at 1.0 *inside* the
transfer functions, before the shoulder could act — PrintFilm, Bleach and
Punch measured **0.0–0.5 CV per stop** above +4 stops, i.e. no highlight
at all. Fix: `eotf709`/`oetf709` extend above 1.0 instead of clamping,
`hue_zone` detects hue on a normalised copy while operating on the
over-range original, and `channel_curve` preserves the over-range
remainder. Everything now clamps once, at the very end. Separately, the
closing shoulder had to be normalised — without it peak white landed at
0.885 and the whole pack read washed out.

---

## Sources

- [DJI Osmo Pocket 4P downloads (LUTs, ACES workflow PDFs)](https://www.dji.com/downloads/products/osmo-pocket-4p)
- [DJI *D-Log2 Recommended ACES Workflow* (PDF)](https://terra-1-g.djicdn.com/6189933d30024fc1b331bffe4fe41837/osmo-pocket-4p/Documents/D-Log2_Recommended_ACES_Workflow_EN.pdf)
- [DJI *White Paper on D-Log and D-Gamut*, Zenmuse X9 (PDF)](https://dl.djicdn.com/downloads/DJI_Ronin_4D/X9_D_Log_D_Gamut_Whitepaper.pdf)
- [CineD — Osmo Pocket 4P released: dual lens, 1-inch sensor, 10-bit D-Log 2](https://www.cined.com/dji-osmo-pocket-4p-released-dual-lens-design-1-inch-sensor-and-10-bit-d-log-2-recording/)
- [gamut.io — 5 things you should know about D-Log2 on the Osmo Pocket 4P](https://gamut.io/dlog2-osmo-pocket-4p/)
- [JacksBlog — analysis of D-Log 2 and D-Gamut 2](https://jackchou00.com/en/posts/dji-dlog2-dgamut2-analysis/)
- [ACEScentral — CTL transformation D-Log to ACES](https://community.acescentral.com/t/ctl-transformation-dlog-to-aces/3977)
