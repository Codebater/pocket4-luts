"""One-command audio cleanup for DJI Mic recordings.

    python src/enhance_audio.py clip.mp4

Writes clip_audio-enhanced.mp4 next to the original: video stream copied
untouched, audio rebuilt. Nothing is uploaded anywhere.

Why a local chain rather than an AI enhancer: measured on real DJI Mic
footage the signal-to-noise was 36.8 dB, which is already clean. The
actual faults were level (-27.7 LUFS against a -14 target) and 50 Hz
mains hum with a strong 3rd harmonic. Those are exactly the things a
deterministic chain fixes perfectly and an AI re-synthesiser tends to
either ignore or smear. Reach for Adobe Podcast / ElevenLabs when the
recording is genuinely damaged -- heavy room reverb, wind, crowd -- not
when it is quiet and hummy.

Chain, in this order for a reason: hum notches and denoise run BEFORE
the gain stage, so normalisation lifts the voice and not the noise
floor. Loudness is two-pass, because single-pass loudnorm is a dynamic
estimator and undershot the target by 3 dB in testing.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave

import numpy as np

TARGETS = {           # integrated LUFS, true peak dBTP, loudness range
    "social": (-14.0, -1.5, 7.0),      # IG / TikTok / YouTube
    "youtube": (-14.0, -1.5, 7.0),
    "podcast": (-16.0, -1.5, 8.0),
    "broadcast": (-23.0, -2.0, 10.0),
}

STRENGTH = {   # fft denoise amount, comp ratio, comp threshold dB, DFN3 atten dB
    "light": (6, 2.0, -24, 12),
    "normal": (10, 3.0, -22, 24),
    "strong": (16, 4.0, -20, 100),
}


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def detect_mains(path):
    """Return 50 or 60 Hz by looking at the quietest stretch of audio."""
    tmp = tempfile.mktemp(suffix=".wav")
    run(["ffmpeg", "-y", "-v", "error", "-i", path, "-map", "0:a:0",
         "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le", tmp])
    try:
        with wave.open(tmp) as w:
            sr = w.getframerate()
            x = np.frombuffer(w.readframes(w.getnframes()),
                              dtype=np.int16).astype(np.float64) / 32768.0
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    if len(x) < sr:
        return 50, 0.0, 0.0
    win, hop = int(0.4 * sr), int(0.05 * sr)
    rms = np.array([np.sqrt((x[i:i + win] ** 2).mean())
                    for i in range(0, len(x) - win, hop)])
    q = int(np.argmin(rms)) * hop
    seg = x[q:q + win] * np.hanning(win)
    S = np.abs(np.fft.rfft(seg))
    f = np.fft.rfftfreq(win, 1 / sr)

    def peak_db(hz):
        i = int(np.argmin(np.abs(f - hz)))
        nb = np.r_[S[max(0, i - 12):max(0, i - 3)], S[i + 4:i + 13]]
        return 20 * np.log10((S[i] + 1e-12) / (nb.mean() + 1e-12))

    a, b = peak_db(50), peak_db(60)
    return (50 if a >= b else 60), a, b


def is_dual_mono(path):
    """True when both channels carry an identical signal.

    The DJI Mic writes one transmitter to both channels, in which case
    taking a single channel is lossless and halves the bitrate. But it
    can also record two transmitters to separate channels, and collapsing
    that would destroy one person's audio -- so this is checked, never
    assumed.
    """
    r = run(["ffmpeg", "-hide_banner", "-i", path, "-map", "0:a:0",
             "-af", "aeval=val(0)-val(1):c=mono,astats=metadata=1",
             "-f", "null", "-"])
    if "Peak level dB: -inf" in r.stderr:
        return True
    m = re.search(r"Peak level dB:\s*(-?[\d.]+)", r.stderr)
    return bool(m) and float(m.group(1)) < -80.0


def channels_of(path):
    r = run(["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=channels", "-of",
             "default=nw=1:nk=1", path])
    try:
        return int(r.stdout.strip())
    except ValueError:
        return 1


def find_deep_filter():
    """Locate the DeepFilterNet CLI (cargo install deep_filter)."""
    exe = shutil.which("deep-filter") or shutil.which("deep-filter.exe")
    if exe:
        return exe
    cand = os.path.join(os.path.expanduser("~"), ".cargo", "bin",
                        "deep-filter.exe" if os.name == "nt"
                        else "deep-filter")
    return cand if os.path.exists(cand) else None


def neural_denoise(src, mono, workdir, atten_db=None):
    """Run DeepFilterNet3 over the audio and return a denoised wav path.

    Uses the project's own Rust CLI rather than the `deepfilternet` pip
    package: that package pins numpy<2 and imports
    `torchaudio.backend.common`, which modern torchaudio no longer has,
    so it cannot work alongside a current scientific-Python stack. The
    Rust binary has no Python dependencies at all.

    DFN3 is a real speech-enhancement network and runs entirely on this
    machine -- nothing is uploaded. It also pulls down some room reverb,
    which no amount of EQ can do. Returns None if unavailable so the
    caller can fall back rather than crash.

    atten_db caps how much it is allowed to attenuate; leaving some noise
    in usually sounds more natural than a perfectly silent background
    that pumps every time speech starts.
    """
    exe = find_deep_filter()
    if not exe:
        return None

    raw = os.path.join(workdir, "dfn_in.wav")
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", src, "-map", "0:a:0"]
    if mono:
        cmd += ["-af", "pan=mono|c0=c0"]
    cmd += ["-ar", "48000", "-c:a", "pcm_s16le", raw]
    if run(cmd).returncode != 0:
        return None

    outdir = os.path.join(workdir, "dfn")
    os.makedirs(outdir, exist_ok=True)
    dfc = [exe, "--output-dir", outdir, "--compensate-delay"]
    if atten_db:
        # Capping attenuation beats full 100 dB reduction: a background
        # scrubbed to perfect silence pumps audibly every time speech
        # starts and stops. Leaving a little room tone sounds natural.
        dfc += ["--atten-lim-db", str(atten_db)]
    dfc.append(raw)
    r = run(dfc)
    produced = [f for f in os.listdir(outdir) if f.lower().endswith(".wav")]
    if not produced:
        sys.stderr.write((r.stderr or "")[-600:] + "\n")
        return None
    return os.path.join(outdir, produced[0])


def measure(path):
    r = run(["ffmpeg", "-hide_banner", "-i", path, "-map", "0:a:0",
             "-af", "loudnorm=print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise SystemExit("could not measure loudness -- is there an audio "
                         f"stream in {path}?")
    return json.loads(m.group(0))


# Voice EQ profiles: (highpass Hz, [(freq, Q-width, gain), ...], deess)
#
# Tuned against a measured DJI Mic take rather than copied off a generic
# "podcast EQ" chart. That recording sat at warmth +17.5 dB and mud
# +15.6 dB while presence was -10.2 and air -22, i.e. presence 25.8 dB
# below the mud -- the classic lavalier sound, because the capsule is on
# the chest pointing away from the mouth. Broadcast voice wants that gap
# nearer 12-15 dB, so the podcast profile cuts 200-450 and lifts 2.6-4k
# hard enough to actually matter.
#
# Note the fundamental (100-180 Hz on a male voice) is deliberately left
# alone. Cutting it to kill boom is what makes people sound thin and
# telephone-ish.
EQ_PROFILES = {
    "off": (75, [], 0.0),
    "natural": (75, [(300, 1.2, -2.0), (3400, 1.0, 2.5)], 0.35),
    "podcast": (90, [(250, 1.4, -4.0),     # chest boom
                     (420, 1.2, -3.5),     # boxiness
                     (900, 1.5, -1.5),     # slight honk
                     (2600, 1.1, 4.0),     # presence
                     (4200, 1.2, 3.5),     # consonants / intelligibility
                     (9000, 0.9, 3.0)],    # air the lav position loses
                0.5),
    "radio": (95, [(240, 1.4, -5.5),
                   (420, 1.2, -4.5),
                   (900, 1.5, -2.0),
                   (2600, 1.0, 5.5),
                   (4200, 1.1, 4.5),
                   (9000, 0.9, 4.0)],
              0.6),
    # The house preset. podcast, plus two narrow dips for the only
    # resonances that actually measured in this voice and room (516 Hz
    # boxiness and 6.4 kHz harshness, both +3.3 dB above the spectral
    # trend). Everything else measured smooth -- roughness was 1.11 dB
    # std -- so there is nothing to gain from carving it up further.
    "voice": (90, [(250, 1.4, -4.0),      # chest boom
                   (420, 1.2, -3.0),      # boxiness
                   (516, 3.0, -2.5),      # measured resonance
                   (900, 1.5, -1.5),      # slight honk
                   (2600, 1.1, 4.0),      # presence
                   (4200, 1.2, 3.5),      # consonants
                   (6400, 3.0, -2.5),     # measured harshness
                   (9000, 0.9, 3.0)],     # air
              0.45),
}


def build_chain(mains, nr, ratio, thresh, eq="podcast", denoise=True):
    """Hum notches and EQ before gain, so normalisation lifts the voice
    and not the noise floor.

    Order matters when chaining with another tool: denoise first, then
    tonal work here, then loudness last. Pass denoise=False if something
    like Cleanroom's DeepFilterNet3 has already run -- stacking a second
    denoiser on top costs detail and buys nothing.
    """
    h = mains
    hp, bands, deess = EQ_PROFILES[eq]
    parts = [
        f"highpass=f={hp}:poles=2",
        f"equalizer=f={h}:t=q:w=6:g=-20",          # mains fundamental
        f"equalizer=f={h * 2}:t=q:w=6:g=-8",       # 2nd harmonic
        f"equalizer=f={h * 3}:t=q:w=6:g=-14",      # 3rd, usually the loud one
        f"equalizer=f={h * 4}:t=q:w=6:g=-5",
    ]
    if denoise:
        parts.append(f"afftdn=nr={nr}:nf=-45:tn=1")   # gentle broadband
    parts += [f"equalizer=f={fq}:t=q:w={w}:g={g}" for fq, w, g in bands]
    if deess > 0:
        parts.append(f"deesser=i={deess}")

    # Two stages rather than one. A single compressor doing all the work
    # is what makes a voice sound squashed and lifeless; a fast low-ratio
    # stage catches transients while a slow one rides the overall level,
    # which is how broadcast chains have always done it.
    parts.append(f"acompressor=threshold={thresh}dB:ratio={ratio:.2f}"
                 ":attack=5:release=90:makeup=1.5")           # fast catcher
    parts.append(f"acompressor=threshold={thresh - 4}dB:ratio={1 + ratio / 3:.2f}"
                 ":attack=60:release=500:makeup=1.5")          # slow leveller
    return ",".join(parts)


def main():
    ap = argparse.ArgumentParser(
        description="Clean up DJI Mic audio in one pass.")
    ap.add_argument("input")
    ap.add_argument("-o", "--output")
    ap.add_argument("--target", choices=sorted(TARGETS), default="social")
    ap.add_argument("--strength", choices=sorted(STRENGTH), default="normal")
    ap.add_argument("--eq", choices=sorted(EQ_PROFILES), default="voice",
                    help="voice EQ profile (default: voice)")
    ap.add_argument("--denoise", choices=("off", "fft", "neural"),
                    default="neural",
                    help="off | fft (built in) | neural (DeepFilterNet3, "
                         "needs the deepfilternet package)")
    ap.add_argument("--mains", type=int, choices=(50, 60),
                    help="force mains frequency instead of detecting it")
    ap.add_argument("--wav", action="store_true",
                    help="write a standalone wav instead of remuxing video")
    a = ap.parse_args()

    if not os.path.exists(a.input):
        raise SystemExit(f"no such file: {a.input}")
    if not shutil.which("ffmpeg"):
        raise SystemExit("ffmpeg not found on PATH")

    I, TP, LRA = TARGETS[a.target]
    nr, ratio, thresh, atten = STRENGTH[a.strength]

    if a.mains:
        mains, m50, m60 = a.mains, 0.0, 0.0
        print(f"mains       : {mains} Hz (forced)")
    else:
        mains, m50, m60 = detect_mains(a.input)
        print(f"mains       : {mains} Hz detected "
              f"(50 Hz {m50:+.1f} dB, 60 Hz {m60:+.1f} dB above neighbours)")

    nch = channels_of(a.input)
    mono_ok = nch > 1 and is_dual_mono(a.input)
    if nch > 1:
        print(f"channels    : {nch}, "
              + ("identical -> collapsing to mono (lossless)" if mono_ok
                 else "genuinely different -> keeping stereo, "
                      "looks like two transmitters"))

    before = measure(a.input)
    print(f"before      : {float(before['input_i']):.1f} LUFS   "
          f"peak {float(before['input_tp']):.1f} dBTP   "
          f"range {float(before['input_lra']):.1f} LU")

    workdir = tempfile.mkdtemp(prefix="enh_")
    audio_src = None
    if a.denoise == "neural":
        print(f"denoise     : DeepFilterNet3 on-device "
                  f"(attenuation limit {atten} dB)...")
        audio_src = neural_denoise(a.input, mono_ok, workdir, atten)
        if audio_src is None:
            print("  deepfilternet not available -- falling back to fft.\n"
                  "  it needs a Rust toolchain (https://rustup.rs) to "
                  "build, or\n"
                  "  run the file through Cleanroom first and use "
                  "--denoise off")
            a.denoise = "fft"

    chain = build_chain(mains, nr, ratio, thresh, a.eq,
                        denoise=(a.denoise == "fft"))

    # pass 1: measure the chain's output so loudnorm can hit the target
    # exactly instead of estimating it on the fly
    print(f"pass 1/2    : analysing (eq={a.eq}, strength={a.strength})...")
    r = run(["ffmpeg", "-hide_banner", "-i", a.input, "-map", "0:a:0",
             "-af", f"{chain},loudnorm=I={I}:TP={TP}:LRA={LRA}"
                    ":print_format=json", "-f", "null", "-"])
    m = re.search(r"\{[^{}]*\"input_i\"[^{}]*\}", r.stderr, re.S)
    if not m:
        raise SystemExit("loudness analysis failed:\n" + r.stderr[-1500:])
    s = json.loads(m.group(0))

    ln = (f"loudnorm=I={I}:TP={TP}:LRA={LRA}"
          f":measured_I={s['input_i']}:measured_TP={s['input_tp']}"
          f":measured_LRA={s['input_lra']}:measured_thresh={s['input_thresh']}"
          f":offset={s['target_offset']}:linear=true:print_format=summary")

    # Two separate traps here, both found by measuring the output rather
    # than trusting the filters:
    #
    # 1. loudnorm's linear mode does NOT enforce the true-peak ceiling.
    #    Left alone it delivered +1.6 dBTP, which clips on playback. So a
    #    real true-peak limiter goes after it.
    # 2. AAC then overshoots the limiter. Measured: a clean -1.5 dBTP wav
    #    came back as +1.6 dBTP once encoded, because lossy codecs do not
    #    preserve peak. So the ceiling is pulled down and the result is
    #    re-measured until the encoded file actually behaves.
    out = a.output or (os.path.splitext(a.input)[0] +
                       ("_audio-enhanced.wav" if a.wav
                        else "_audio-enhanced.mp4"))

    # Collapse to mono inside the filtergraph, never with the -ac output
    # option: -ac 1 into the AAC encoder produced +1.63 dBTP from a signal
    # that was -0.99 dBTP by every other route. Same waveform, 2.6 dB of
    # phantom peak. pan= is explicit and behaves.
    downmix = ",pan=mono|c0=c0" if (mono_ok and not audio_src) else ""

    def render(trim_db, headroom_db):
        ceiling = 10 ** ((TP - headroom_db) / 20.0)
        limiter = (f"alimiter=limit={ceiling:.4f}:attack=5:release=50"
                   f":level=false:asc=1")
        vol = f",volume={trim_db:.2f}dB" if abs(trim_db) > 0.01 else ""
        af = f"{chain}{downmix},{ln}{vol},{limiter}"
        asrc = audio_src or a.input
        if a.wav:
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", asrc,
                   "-map", "0:a:0", "-af", af, "-ar", "48000",
                   "-c:a", "pcm_s16le", out]
        elif audio_src:
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", a.input,
                   "-i", audio_src, "-map", "0:v:0", "-map", "1:a:0",
                   "-c:v", "copy", "-af", af, "-ar", "48000",
                   "-c:a", "aac", "-b:a", "192k",
                   "-movflags", "+faststart", out]
        else:
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", a.input,
                   "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy",
                   "-af", af, "-ar", "48000",
                   "-c:a", "aac", "-b:a", "192k",
                   "-movflags", "+faststart", out]
        r = run(cmd)
        if r.returncode != 0:
            raise SystemExit("render failed:\n" + r.stderr[-1500:])
        return measure(out)

    print("pass 2/2    : rendering...")
    trim, headroom, prev_i = 0.0, 0.0, None
    after = render(trim, headroom)
    for _ in range(3):
        ai, atp = float(after["input_i"]), float(after["input_tp"])
        over, off = atp - TP, I - ai
        if over <= 0.1 and abs(off) <= 0.5:
            break
        # Once the limiter is absorbing the gain, more trim buys nothing
        # but squash. Stop rather than grinding the transients flat to
        # chase the last half a dB nobody can hear.
        if over <= 0.1 and prev_i is not None and abs(ai - prev_i) < 0.2:
            print(f"limiter is absorbing further gain -- stopping at "
                  f"{ai:.1f} LUFS rather than over-compressing")
            break
        prev_i = ai
        if over > 0.1:
            headroom += over + 0.1
            print(f"encoder overshot by {over:+.1f} dB -> "
                  f"ceiling down to {TP - headroom:.1f} dBTP")
        if abs(off) > 0.5:
            trim += off
            print(f"trim        : {trim:+.2f} dB")
        after = render(trim, headroom)

    ai, atp = float(after["input_i"]), float(after["input_tp"])
    print(f"after       : {ai:.1f} LUFS   peak {atp:.1f} dBTP   "
          f"range {float(after['input_lra']):.1f} LU")
    print(f"gain applied: {ai - float(before['input_i']):+.1f} dB")
    if atp > 0.0:
        print("WARNING: true peak is above 0 dBTP and will clip")
    elif abs(ai - I) > 1.0:
        print(f"note: landed {ai - I:+.1f} dB off the {I} LUFS target")
    else:
        print(f"on target ({I} LUFS, ceiling {TP} dBTP)")
    print(f"\nwrote {out}  ({os.path.getsize(out) / 1e6:.1f} MB)")


if __name__ == "__main__":
    sys.exit(main())
