#!/usr/bin/env python3
"""Convert an MITgcm binary pickup file to individual init files.

Reads the pickup.<iter>.data/.meta pair and writes:
  T.init.bin, S.init.bin, U.init.bin, V.init.bin, Eta.init.bin

The pickup is float64 (MITgcm default for checkpoints); init files are
written as float32 (matching readBinaryPrec=32 in data PARM01).

Usage:
    python pickup_to_init.py <pickup_prefix> <output_dir> [--nx 768] [--ny 424] [--nr 50]

Example:
    python pickup_to_init.py repeat-year-50/001/pickup.0000087600 repeat-year-50/002/
"""

import argparse
import re
import sys
from pathlib import Path

import numpy as np


def parse_pickup_meta(meta_path: Path) -> dict:
    """Parse a MITgcm .meta file and return dims, precision, and field list."""
    text = meta_path.read_text()

    # Extract dimensions
    dim_match = re.search(r"dimList\s*=\s*\[\s*([\d\s,]+)\]", text)
    if not dim_match:
        raise ValueError(f"Cannot parse dimList from {meta_path}")
    dims = [int(x) for x in dim_match.group(1).replace(",", " ").split()]
    nx, ny = dims[0], dims[3]

    # Extract precision
    prec_match = re.search(r"dataprec\s*=\s*\[\s*'(\w+)'\s*\]", text)
    dtype = np.float64 if prec_match and "64" in prec_match.group(1) else np.float32

    # Extract number of records
    nrec_match = re.search(r"nrecords\s*=\s*\[\s*(\d+)\s*\]", text)
    nrecords = int(nrec_match.group(1)) if nrec_match else None

    # Extract field list
    fld_match = re.search(r"fldList\s*=\s*\{([^}]+)\}", text)
    if not fld_match:
        raise ValueError(f"Cannot parse fldList from {meta_path}")
    fields = re.findall(r"'(\w+)\s*'", fld_match.group(1))

    return {"nx": nx, "ny": ny, "dtype": dtype, "nrecords": nrecords, "fields": fields}


def pickup_to_init(pickup_prefix: str, output_dir: str, nx: int, ny: int, nr: int):
    """Read a pickup file and write individual init .bin files."""
    meta_path = Path(pickup_prefix + ".meta")
    data_path = Path(pickup_prefix + ".data")
    out = Path(output_dir)

    if not meta_path.exists():
        raise FileNotFoundError(f"Meta file not found: {meta_path}")
    if not data_path.exists():
        raise FileNotFoundError(f"Data file not found: {data_path}")

    meta = parse_pickup_meta(meta_path)
    dtype = meta["dtype"]
    fields = meta["fields"]
    rec_size = nx * ny

    print(f"Pickup: {data_path}")
    print(f"  Grid: {nx} x {ny} x {nr}")
    print(f"  Precision: {dtype}")
    print(f"  Fields: {fields}")
    print(f"  Total records: {meta['nrecords']}")

    # Map pickup field names to init file names and their depth (nr for 3D, 1 for 2D)
    field_map = {
        "Uvel": ("U.init.bin", nr),
        "Vvel": ("V.init.bin", nr),
        "Theta": ("T.init.bin", nr),
        "Salt": ("S.init.bin", nr),
        "EtaN": ("Eta.init.bin", 1),
    }

    # Compute byte offsets for each field in the pickup
    bytes_per_val = np.dtype(dtype).itemsize
    rec_bytes = rec_size * bytes_per_val

    # Build offset table: walk through fields in order
    offsets = {}
    current_rec = 0
    for fld in fields:
        # 3D fields have nr levels, 2D fields have 1 level
        if fld in ("EtaN", "dEtaHdt", "EtaH"):
            nlevels = 1
        else:
            nlevels = nr
        offsets[fld] = (current_rec, nlevels)
        current_rec += nlevels

    print(f"  Computed record layout: {offsets}")

    # Read and write the fields we need
    out.mkdir(parents=True, exist_ok=True)
    with open(data_path, "rb") as f:
        for fld_name, (init_name, nlevels) in field_map.items():
            if fld_name not in offsets:
                print(f"  WARNING: field '{fld_name}' not found in pickup, skipping")
                continue

            start_rec, expected_levels = offsets[fld_name]
            assert expected_levels == nlevels, (
                f"Level mismatch for {fld_name}: expected {nlevels}, got {expected_levels}"
            )

            # Seek to field start and read
            f.seek(start_rec * rec_bytes)
            data = np.fromfile(f, dtype=dtype, count=rec_size * nlevels)
            data = data.reshape((nlevels, ny, nx))

            # Convert to float32 for init files
            init_path = out / init_name
            data.astype(np.float32).tofile(init_path)
            size_mb = init_path.stat().st_size / 1e6
            print(f"  Wrote {init_path} ({size_mb:.1f} MB)")

    print("Done.")


def main():
    parser = argparse.ArgumentParser(description="Convert MITgcm pickup to init files")
    parser.add_argument("pickup_prefix", help="Path prefix (without .data/.meta)")
    parser.add_argument("output_dir", help="Directory to write init files")
    parser.add_argument("--nx", type=int, default=768, help="Grid points in X")
    parser.add_argument("--ny", type=int, default=424, help="Grid points in Y")
    parser.add_argument("--nr", type=int, default=50, help="Grid points in Z")
    args = parser.parse_args()

    pickup_to_init(args.pickup_prefix, args.output_dir, args.nx, args.ny, args.nr)


if __name__ == "__main__":
    main()
