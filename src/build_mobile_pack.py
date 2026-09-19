"""Package a phone-friendly zip of the pack.

33-point only: several mobile editors refuse to load 65-point cubes, and
at phone screen size the difference is not visible anyway. Flat structure
with no nested folders, because extracting and browsing a nested zip on a
phone is miserable.

Written with Python's zipfile rather than PowerShell Compress-Archive so
the entries use forward slashes and unpack correctly everywhere.
"""
from __future__ import annotations

import glob
import os
import shutil
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "dist")
NAME = "POCKET4P_DLog2_LUTs_Mobile_v1.0"

READ_ME = """POCKET 4P - D-Log 2 LUT Pack v1.0  (mobile / 33-point)
=======================================================

For footage shot on the DJI Osmo Pocket 4P in D-Log 2. Not for D-Log,
not for Normal, not for any other camera.


WHICH ONE
---------
04_PrintFilm   dense blacks, warm highlights, cool shadow toe.  <- start here
03_Natural     true to life, warm skin, honest greens. Everyday.
01_Neutral     reference render. Correct, no opinion.
02_FlatBase    low contrast base to grade on top of. Not a finished look.

05_TealAmber   commercial teal/orange, skin protected
06_Bleach      bleach bypass, high contrast, colour pulled out
07_NightNeon   interiors and night, open shadows, magenta/cyan
08_Golden      warm golden-hour bias
09_Nordic      cold, muted, overcast
10_Mono        black and white, orange-filter response
11_RetroFade   faded stock, milky blacks, cyan shadows
12_Punch       high contrast and saturation, reads at thumbnail size


GETTING THEM ONTO THE PHONE
---------------------------
iPhone    AirDrop the zip to yourself, tap it in Files, it unzips in
          place. Leave the .cube files in Files - do not try to put
          them in Photos.
Android   Copy the zip to Downloads, extract with your file manager.


APPS
----
Mobile LUT support is genuinely inconsistent, so in order of reliability:

LumaFusion (iOS/iPadOS)      Reliable. Import the .cube, then apply it
                             as a LUT preset on the clip.
DaVinci Resolve for iPad     Reliable. Same LUT workflow as desktop.
CapCut mobile                Version dependent. Recent builds have an
                             LUT import under the clip's adjust/filter
                             panel; older builds have no custom LUT
                             import at all. If you cannot find it, your
                             version does not have it.
VN Video Editor              Version dependent, same story as CapCut.
Filmic Pro / Protake         For monitoring the look while shooting,
                             not for baking it into the file.

If your editor has no LUT import, grade on a desktop instead - the
65-point versions of these are sharper and live alongside this pack.


TWO THINGS THAT WILL RUIN IT
----------------------------
1. Do not stack these on top of another D-Log LUT. If your app applies
   a DJI camera LUT automatically, turn it off first.
2. These expect D-Log 2. Applying them to normal footage will look
   broken, and that is expected.


SHOOTING SO THEY WORK
---------------------
D-Log 2 puts middle grey at about 31 IRE - far lower than you expect.
It looks underexposed on the camera screen when it is correct.

  18% grey card ....... 31 IRE   (10-bit code 312)
  skin ................ 33-37 IRE
  white shirt ......... 45 IRE
  sensor clips ........ about 92 IRE

There are roughly 10 stops above middle grey and only 5.6 below, so if
in doubt, overexpose. Underexposed D-Log 2 is what makes this camera
look cheap. Shoot 10-bit HEVC - 8-bit log will band.

LOOKS_PREVIEW.jpg shows every look on the same frame.
"""


def main():
    src = sorted(glob.glob(os.path.join(ROOT, "luts", "*_size33.cube")))
    if not src:
        raise SystemExit("no 33-point LUTs built - run build_luts.py 33")
    os.makedirs(OUT, exist_ok=True)
    zpath = os.path.join(OUT, NAME + ".zip")

    preview = None
    for cand in ("looks_door.jpg", "looks_skin.jpg"):
        p = os.path.join(ROOT, "preview", cand)
        if os.path.exists(p):
            preview = p
            break

    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for f in src:
            # drop the _size33 suffix; everything in here is 33-point
            arc = os.path.basename(f).replace("_size33", "")
            z.write(f, arc)
        z.writestr("README.txt", READ_ME.replace("\n", "\r\n"))
        if preview:
            z.write(preview, "LOOKS_PREVIEW.jpg")

    # also leave the cubes loose, for transfers where a zip is awkward
    loose = os.path.join(OUT, NAME)
    shutil.rmtree(loose, ignore_errors=True)
    os.makedirs(loose)
    for f in src:
        shutil.copy2(f, os.path.join(
            loose, os.path.basename(f).replace("_size33", "")))
    with open(os.path.join(loose, "README.txt"), "w", newline="\r\n") as fh:
        fh.write(READ_ME)
    if preview:
        shutil.copy2(preview, os.path.join(loose, "LOOKS_PREVIEW.jpg"))

    mb = os.path.getsize(zpath) / 1e6
    print(f"{zpath}  ({mb:.1f} MB)")
    with zipfile.ZipFile(zpath) as z:
        bad = z.testzip()
        print(f"  integrity: {'FAIL ' + str(bad) if bad else 'ok'}")
        for i in z.infolist():
            print(f"    {i.filename:32s} {i.file_size / 1000:8.1f} kB")
    print(f"\nloose copy: {loose}")


if __name__ == "__main__":
    main()
