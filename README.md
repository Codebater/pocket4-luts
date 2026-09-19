# POCKET 4P — D-Log 2 LUT Pack v1.0

12 LUTs for **DJI Osmo Pocket 4P** footage shot in **D-Log 2**, in 33- and
65-point `.cube`.

Built on DJI's own official D-Log2 → Rec.709 colorimetry, with their
highlight clipping removed. Measured against their file:

| | +4→+8 stops | +6→+10 stops | of range sent to pure white |
|---|---|---|---|
| DJI official LUT | 30.9 CV/stop | 9.1 CV/stop | **13.0%** |
| **P4P Neutral** | 29.5 CV/stop | **12.2 CV/stop** | **1.7%** |

Mid-tones and skin come through **identical to DJI** — measured deviation
below the knee is **0.00 code values** at 65-point — while the top end
keeps its separation instead of being flattened into white.

**What this is honestly worth.** The 13.0% → 1.7% figure is measured on a
synthetic ramp covering the full D-Log2 range. On real footage the gain
depends entirely on whether your scene actually exceeds +7 stops above
middle grey. Measured on a real interior clip peaking at +8.1 stops,
neither LUT hard-clipped, and the pack held **14–22% more tonal
separation above +6 stops** while giving up 3–10% between +5 and +6.
The transform redistributes highlight range — it does not invent
detail the sensor never captured. Expect a large difference on skies,
sun and windows shot from indoors, and a modest one on flat interiors.

---

## The LUTs

**Start here**

| | |
|---|---|
| **01 Neutral** | The reference render. DJI's colour and contrast, highlights intact. Use this when you want it to just look right. |
| **02 FlatBase** | Low-contrast base to grade on top of. Not a finished image — a starting point. |

**Everyday**

| | |
|---|---|
| **03 Natural** | True-to-life, skin nudged warm, greens kept honest. The daily driver. |
| **12 Punch** | High contrast and saturation. Reads at thumbnail size and on a phone outdoors. |

**Film-referenced**

| | |
|---|---|
| **04 PrintFilm** | Photochemical print feel — dense blacks, warm highlights, cool shadow toe. |
| **06 Bleach** | Bleach bypass. Contrast up, most of the colour pulled out. |
| **11 RetroFade** | Faded stock. Lifted milky blacks, cyan shadows, soft top end. |
| **10 Mono** | Black and white, orange-filter response, warm print tone. |

**Situational**

| | |
|---|---|
| **05 TealAmber** | Commercial teal/orange with skin protected from the shift. |
| **07 NightNeon** | Interiors and after dark. Shadows kept open, magenta/cyan separation. |
| **08 Golden** | Warm golden-hour bias, amber highlights. |
| **09 Nordic** | Cold and muted. Overcast, slate greens. |

**33 vs 65 point:** 65 is more precise in saturated colour and worth it
for delivery. 33 loads faster and is what mobile apps prefer. Identical
looks otherwise.

---

## Installing

**DaVinci Resolve** — copy the `.cube` files into the LUT folder
(*Project Settings → Color Management → Open LUT Folder*), then
*Refresh*. Apply on a node, or as a **Timeline LUT**. Right-click a clip →
*3D LUT* also works.

**Premiere Pro** — *Lumetri Color → Creative → Look → Browse…* and pick
the file. For a technical-first workflow put it under *Basic Correction →
Input LUT* instead.

**Final Cut Pro** — add the **Custom LUT** effect to the clip, set *LUT*
to *Choose Custom LUT…*. Set the clip's camera LUT to *None* first so you
aren't stacking two transforms.

**CapCut / LumaFusion / VN** — import as a custom LUT/filter. Use the
**33-point** files; several mobile apps won't load 65-point.

**Photoshop / After Effects** — *Color Lookup* adjustment layer, or the
*Apply Color LUT* effect.

**ffmpeg**

```bash
ffmpeg -i input.mp4 -vf "lut3d=file='P4P_01_Neutral_size65.cube':interp=tetrahedral" -c:v libx264 -crf 16 output.mp4
```

### Two things that will bite you

1. **Turn off any other D-Log LUT first.** If your NLE auto-applies a DJI
   camera LUT, these stack and the result is unusable.
2. **These expect full-range D-Log 2.** If your NLE tags the clip as
   limited range (16–235), the blacks will crush and the highlights will
   blow. In Resolve, set the clip to *Full* range in the Clip Attributes
   if it looks wrong.

---

## Shooting D-Log 2 so these work

D-Log 2 puts middle grey **much lower than you expect** — about 31 IRE,
against ~41 for D-Log M and ~46 for Rec.709. It looks underexposed on the
screen when it is correct. That low placement is what buys the highlight
range.

Derived from the curve (`src/dlog2.py`):

| Subject | Reflectance | Stops | 10-bit CV | IRE |
|---|---|---|---|---|
| Black floor | 0% | — | 64 | 6 |
| Deep shadow | 1.1% | −4 | 96 | 9 |
| Shadow | 4.5% | −2 | 187 | 18 |
| **18% grey card** | **18%** | **0** | **312** | **31** |
| Skin (average) | 28.6% | +0.67 | 354 | 35 |
| White shirt / 90% white | 90% | +2.3 | 457 | 45 |
| Bright sky, window | 576% | +5 | 625 | 61 |
| *DJI's LUT clips past here* | 2304% | +7 | 750 | 73 |
| Sensor clip | ~18400% | +10 | ~938 | 92 |

Practical version:

- **Put skin around 33–37 IRE.** Not 50. It will look flat and dark on the
  screen; that is correct.
- **Zebras at 90–95** catch the real clip point, not the LUT's.
- **Expose to the right if the scene is flat** — up to a stop over is
  fine and buys you cleaner shadows, since there are ~10 stops of room
  above grey and only ~5.6 below. Underexposing D-Log 2 is the one thing
  that will make it look noisy and cheap.
- **ISO 100 is the base.** D-Log 2 runs 100–3200 on this camera.
- Shoot **HEVC 10-bit**. 8-bit log will band under any of these LUTs.

---

## Audio — DJI Mic cleanup

**Drag files onto `ENHANCE-AUDIO.bat`.** That's the whole workflow —
one or several at a time. Each comes back out next to the original as
`NAME_audio-enhanced.mp4`, video untouched, audio rebuilt.

Or from a terminal:

```bash
python src/enhance_audio.py DJI_0001.MP4
```

Nothing is uploaded anywhere.

Targets: `--target social` (−14 LUFS, default), `podcast` (−16),
`broadcast` (−23). Strength: `--strength light|normal|strong`.
`--wav` writes a standalone file instead of remuxing.

### Voice EQ

`--eq off | natural | podcast | radio` — **`podcast` is the default.**

Not copied off a generic "podcast EQ" chart. The measured DJI Mic take
sat at warmth +17.5 dB and mud +15.6 dB while presence was −10.2 and air
−22 — presence **25.8 dB below the mud**, which is the classic lavalier
sound, because the capsule is on your chest pointing away from your
mouth. A broadcast voice wants that gap nearer 12–15 dB.

Measured on speech-only frames, presence minus mud:

| profile | presence − mud | |
|---|---|---|
| source | −25.8 dB | boomy and muffled |
| `off` | −23.8 dB | hum + level only |
| `natural` | −20.8 dB | gentle, safest on an already-good mic |
| `podcast` | −14.8 dB | generic broadcast shape |
| **`voice`** | **−13.5 dB** | **the house preset — default** |
| `radio` | −12.1 dB | aggressive, for noisy playback |

All of them take presence from −10.2 to around 0 dB and air from −22.0 to
−12 while **leaving the 100–180 Hz fundamental alone** — cutting that to
kill boom is exactly what makes people sound thin and telephone-ish.

`voice` is `podcast` plus dips at the only two resonances that actually
measured in this voice and room — **516 Hz** boxiness and **6.4 kHz**
harshness, both +3.3 dB above the spectral trend. Nothing else needed
carving: measured roughness was 1.11 dB std. Against `podcast` it lands
the 516 Hz peak 1.7 dB lower, the 6.4 kHz harshness 1.6 dB lower, and
keeps 0.7 dB more fundamental, so it's smoother and a little fuller.

Levelling is **two-stage** — a fast low-ratio stage catching transients
and a slow one riding overall level. One compressor doing all the work is
what makes a voice sound squashed.

It measures the recording first and tells you what it found — mains
frequency, whether the channels are identical, loudness before and after.

Measured on a real DJI Mic take:

| | before | after |
|---|---|---|
| Loudness | −27.7 LUFS | **−14.7 LUFS** |
| True peak | −8.0 dBTP | −1.4 dBTP (no clipping) |
| Range | 14.1 LU | 9.4 LU |
| 50 Hz mains hum | +13.6 dB | **−5.0 dB** |
| 150 Hz harmonic | +11.2 dB | **+2.0 dB** |

### Chaining with a neural denoiser

[Cleanroom](https://github.com/bluejacketblackhawk/cleanroom) (MIT, local,
Rust/Tauri) masters with **DeepFilterNet3** — a proper on-device neural
denoiser, much stronger than the `afftdn` here for room noise, hiss and
fans. It also does transcription with diarization. What it does *not*
document is any EQ, notch or de-ess stage, so it will not touch mains hum
or a lavalier's presence dip.

They compose. Correct order is **denoise → tonal work → loudness last**:

```bash
python src/enhance_audio.py cleanroom_output.wav --denoise off
```

`--denoise off` skips the broadband stage so the signal is not denoised
twice, and still applies hum notches, voice EQ and final loudness.

### Denoisers

`--denoise neural | fft | off` — **`neural` is the default**, running
DeepFilterNet3 locally. Nothing is uploaded.

Measured on a 12 dB SNR version of a real take, against the clean
original. Noise is compared *after level-matching on speech*, because the
chain normalises loudness and raw noise floors are otherwise not
comparable:

| variant | noise vs clean | speech distortion |
|---|---|---|
| noisy input | +17.0 dB | 1.85 dB |
| `off` | +23.0 dB | 5.25 dB |
| `fft` (afftdn) | +18.2 dB | 3.58 dB |
| **`neural`** (DFN3) | **+3.6 dB** | **2.30 dB** |

Both columns matter. Noise reduction alone is a meaningless score — a
filter that deletes everything wins it — so speech distortion measures
how far the voice's own spectrum drifted from the clean reference. DFN3
wins on both: within 3.6 dB of the original noise floor, 14.6 dB better
than `afftdn`, while distorting the voice least.

`--strength` sets the attenuation limit: light 12 dB, normal 24 dB,
strong 100 dB (full). Capping it beats full reduction — a background
scrubbed to perfect silence pumps audibly every time speech starts.

**Installing DeepFilterNet3.** The `deepfilternet` pip package is a dead
end: it pins `numpy<2` and imports `torchaudio.backend.common`, which
modern torchaudio no longer has. Build the Rust CLI instead:

```bash
cargo install --git https://github.com/Rikorose/DeepFilterNet --tag v0.5.6 --bin deep-filter --features "bin,tract,wav-utils,transforms" deep_filter
```

If that fails on the pinned `time` crate (it does not compile on rustc
1.98), clone the tag, run `cargo update -p time`, and build from inside
`libDF/` — building from the workspace root drags in `dataset`, which
needs system HDF5 the binary never uses.

**Why not an AI enhancer.** That take measured 36.8 dB signal-to-noise —
it was already clean. The faults were level and mains hum, which a
deterministic chain fixes exactly and an AI re-synthesiser tends to
either ignore or smear. Use Adobe Podcast Enhance or ElevenLabs Voice
Isolator when a recording is genuinely damaged — heavy room reverb, wind,
crowd, or rescuing camera audio because the mic failed. Not for this.

**Three traps this works around**, all found by measuring output rather
than trusting filters:

1. Single-pass `loudnorm` is a dynamic estimator and undershot by 3 dB.
   Loudness is measured first, then applied.
2. `loudnorm`'s `linear=true` does **not** enforce the true-peak ceiling —
   it delivered +1.6 dBTP, which clips. A real limiter follows it.
3. `-ac 1` into the AAC encoder produced **+1.63 dBTP** from a signal that
   measured −0.99 dBTP by every other route — 2.6 dB of phantom peak from
   the same waveform. Mono collapse happens with `pan=` inside the
   filtergraph instead, and only after checking the channels really are
   identical (the DJI Mic can put two transmitters on separate channels,
   and collapsing that would delete someone).

## What's here

```
luts/      the 24 .cube files (12 looks x 33 and 65 point)
vendor/    DJI's official D-Log2 -> Rec.709 cubes, used as the base
src/       the generator: curve model, look engine, builder, validator
docs/      COLOR-SCIENCE.md - full derivation, measurements and sources
preview/   contact sheets
ref/       reference frames
```

Rebuild, check and preview:

```bash
python src/build_luts.py 33 65
```

```bash
python src/validate.py 65
```

```bash
python src/preview.py path/to/DJI_0001.MP4 --frames 3
```

Tune a look against real footage rather than by eye — reports how much
each LUT tints neutral surfaces, plus skin hue, saturation and luma:

```bash
python src/measure_looks.py frame.png --size 65
```

---

## Honesty about the colour science

DJI has **not published a D-Log 2 white paper**. The transfer curve in
`src/dlog2.py` is a **model fitted to published anchors** (middle grey at
CV 312, ceiling at 47500% reflectance, ~17 stops), not DJI's math. It
independently predicts that CV 940 sits at +10.04 stops — which is exactly
where DJI's own LUT stops responding, and matches third-party profiling of
"~10 stops above grey before hard clip". That agreement is why it's
trustworthy enough to build on.

We deliberately ship **no D-Gamut2 matrix**: two separate attempts to
recover one from DJI's LUT failed honestly (a global fit at 122 CV RMS, a
Jacobian method that drifted with luminance because DJI ramp saturation
with brightness). Rather than invent one, the pack routes colour through
DJI's official cube, which contains their real colorimetry.

Full derivation, every measurement and all sources: **[docs/COLOR-SCIENCE.md](docs/COLOR-SCIENCE.md)**.
