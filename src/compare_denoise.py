"""Compare denoisers honestly: how much noise goes, how much voice survives.

    python src/compare_denoise.py clean.wav noisy.wav

Noise reduction on its own is a useless number -- a filter that deletes
everything scores perfectly. So this reports both sides:

  noise removed    dB drop in the non-speech stretches (higher is better)
  speech distortion  how far the speech spectrum moved away from the
                     clean reference (LOWER is better)

A good denoiser wins on both. A bad one buys the first with the second.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import wave

import numpy as np


def load(path):
    with wave.open(path) as w:
        sr, nch = w.getframerate(), w.getnchannels()
        x = np.frombuffer(w.readframes(w.getnframes()),
                          dtype=np.int16).astype(np.float64) / 32768.0
    if nch > 1:
        x = x.reshape(-1, nch).mean(1)
    return x, sr


def frames(x, win=2048, hop=1024):
    return np.array([x[i:i + win] for i in range(0, len(x) - win, hop)])


def analyse(clean, test, sr):
    n = min(len(clean), len(test))
    c, t = clean[:n], test[:n]
    fc, ft = frames(c), frames(t)
    rms_c = np.sqrt((fc ** 2).mean(1))
    speech = rms_c > rms_c.max() * 10 ** (-18 / 20)
    quiet = rms_c < np.percentile(rms_c, 20)

    # The chain normalises loudness, so raw noise-floor levels are not
    # comparable -- everything gets louder together. Match the two files
    # on speech level first, then the quiet-frame difference is a real
    # measure of noise relative to voice.
    sc = np.sqrt((fc[speech] ** 2).mean()) + 1e-12
    st = np.sqrt((ft[speech] ** 2).mean()) + 1e-12
    ft = ft * (sc / st)

    noise_before = 20 * np.log10(np.sqrt((fc[quiet] ** 2).mean()) + 1e-12)
    noise_after = 20 * np.log10(np.sqrt((ft[quiet] ** 2).mean()) + 1e-12)

    W = np.hanning(2048)
    Sc = np.abs(np.fft.rfft(fc[speech] * W, axis=1)).mean(0)
    St = np.abs(np.fft.rfft(ft[speech] * W, axis=1)).mean(0)
    f = np.fft.rfftfreq(2048, 1 / sr)
    band = (f > 200) & (f < 8000)
    # normalise out level, then measure spectral divergence in the voice band
    Sc_n = Sc[band] / (np.sqrt((Sc[band] ** 2).mean()) + 1e-12)
    St_n = St[band] / (np.sqrt((St[band] ** 2).mean()) + 1e-12)
    dist = np.sqrt(((20 * np.log10(St_n + 1e-9)
                     - 20 * np.log10(Sc_n + 1e-9)) ** 2).mean())
    return noise_after - noise_before, dist


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    clean_p, noisy_p = sys.argv[1], sys.argv[2]
    clean, sr = load(clean_p)
    tmp = tempfile.mkdtemp(prefix="dncmp_")
    here = os.path.dirname(__file__)

    variants = {"no denoise": ["--denoise", "off"],
                "fft (afftdn)": ["--denoise", "fft"],
                "neural (DFN3)": ["--denoise", "neural"]}
    print(f"{'variant':>16} {'noise removed':>15} {'speech distortion':>19}")
    noisy, _ = load(noisy_p)
    d, dist = analyse(clean, noisy, sr)
    print(f"{'noisy input':>16} {d:>13.1f} dB {dist:>17.2f} dB")
    for name, flags in variants.items():
        out = os.path.join(tmp, name.split()[0] + ".wav")
        r = subprocess.run(
            [sys.executable, os.path.join(here, "enhance_audio.py"), noisy_p,
             "--eq", "off", "--wav", "-o", out] + flags,
            capture_output=True, text=True)
        if not os.path.exists(out):
            print(f"{name:>16} {'failed':>15}   {r.stdout.strip()[-60:]}")
            continue
        test, _ = load(out)
        d, dist = analyse(clean, test, sr)
        print(f"{name:>16} {d:>13.1f} dB {dist:>17.2f} dB")
    print("\nnoise removed: more negative is better")
    print("speech distortion: LOWER is better -- how far the voice moved")


if __name__ == "__main__":
    main()
