"""Minimal .cube 3D-LUT read/write/sample utilities.

Everything here works in float RGB, no clamping unless asked, so the
caller controls where signal gets clipped.
"""
from __future__ import annotations

import numpy as np


def read_cube(path):
    """Read a .cube 3D LUT. Returns (table, size, domain_min, domain_max).

    table has shape (size, size, size, 3) indexed [b, g, r] because .cube
    files vary red fastest.
    """
    size = None
    dmin = np.array([0.0, 0.0, 0.0])
    dmax = np.array([1.0, 1.0, 1.0])
    rows = []
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            head = line.split()[0].upper()
            if head == "LUT_3D_SIZE":
                size = int(line.split()[1])
            elif head == "DOMAIN_MIN":
                dmin = np.array([float(v) for v in line.split()[1:4]])
            elif head == "DOMAIN_MAX":
                dmax = np.array([float(v) for v in line.split()[1:4]])
            elif head in ("TITLE", "LUT_1D_SIZE", "LUT_1D_INPUT_RANGE",
                          "LUT_3D_INPUT_RANGE"):
                continue
            else:
                parts = line.split()
                if len(parts) == 3:
                    rows.append([float(p) for p in parts])
    if size is None:
        raise ValueError(f"{path}: no LUT_3D_SIZE")
    table = np.array(rows, dtype=np.float64)
    if table.shape[0] != size ** 3:
        raise ValueError(f"{path}: expected {size**3} rows, got {table.shape[0]}")
    return table.reshape(size, size, size, 3), size, dmin, dmax


def sample_cube(table, rgb, dmin=None, dmax=None):
    """Trilinearly sample a cube table at float rgb of shape (..., 3)."""
    size = table.shape[0]
    rgb = np.asarray(rgb, dtype=np.float64)
    if dmin is not None:
        rgb = (rgb - dmin) / (dmax - dmin)
    pos = np.clip(rgb, 0.0, 1.0) * (size - 1)
    i0 = np.floor(pos).astype(np.int64)
    i0 = np.clip(i0, 0, size - 2)
    f = pos - i0
    r0, g0, b0 = i0[..., 0], i0[..., 1], i0[..., 2]
    fr, fg, fb = f[..., 0:1], f[..., 1:2], f[..., 2:3]

    def at(dr, dg, db):
        return table[b0 + db, g0 + dg, r0 + dr]

    c00 = at(0, 0, 0) * (1 - fr) + at(1, 0, 0) * fr
    c10 = at(0, 1, 0) * (1 - fr) + at(1, 1, 0) * fr
    c01 = at(0, 0, 1) * (1 - fr) + at(1, 0, 1) * fr
    c11 = at(0, 1, 1) * (1 - fr) + at(1, 1, 1) * fr
    c0 = c00 * (1 - fg) + c10 * fg
    c1 = c01 * (1 - fg) + c11 * fg
    return c0 * (1 - fb) + c1 * fb


def identity_grid(size):
    """Input grid in .cube ordering: shape (size**3, 3), red varies fastest."""
    ax = np.linspace(0.0, 1.0, size)
    b, g, r = np.meshgrid(ax, ax, ax, indexing="ij")
    return np.stack([r, g, b], axis=-1).reshape(-1, 3)


def write_cube(path, rgb_out, size, title=None, comments=()):
    """Write a .cube from a (size**3, 3) array in .cube ordering."""
    rgb_out = np.asarray(rgb_out, dtype=np.float64).reshape(-1, 3)
    if rgb_out.shape[0] != size ** 3:
        raise ValueError("row count does not match size")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        for c in comments:
            fh.write(f"# {c}\n")
        if title:
            fh.write(f'TITLE "{title}"\n')
        fh.write(f"LUT_3D_SIZE {size}\n")
        fh.write("DOMAIN_MIN 0.0 0.0 0.0\n")
        fh.write("DOMAIN_MAX 1.0 1.0 1.0\n\n")
        for r, g, b in rgb_out:
            fh.write(f"{r:.6f} {g:.6f} {b:.6f}\n")
