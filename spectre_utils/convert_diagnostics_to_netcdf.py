"""
convert_diagnostics_to_netcdf.py
================================
Watch for MITgcm binary diagnostics output (.data/.meta) and convert to
per-tile NetCDF files in MNC-compatible directory structure.

This allows downstream tools (plotter, analysis) to work with NetCDF while
the model runs with diag_mnc=.FALSE. to avoid MNC memory leaks.

Usage:
    python convert_diagnostics_to_netcdf.py <run_dir> [--poll 60]
"""

import os
import re
import sys
import time
import glob
import argparse
import numpy as np

_xr = None


def _import_xr():
    global _xr
    if _xr is None:
        import xarray as xr
        _xr = xr


def read_meta(meta_path):
    """Parse a MITgcm .meta file."""
    with open(meta_path, "r") as f:
        text = f.read()

    dims_match = re.search(r"dimList\s*=\s*\[\s*([\d\s,]+)\]", text)
    flds_match = re.search(r"fldList\s*=\s*\{([^}]+)\}", text)
    nflds_match = re.search(r"nFlds\s*=\s*\[\s*(\d+)\s*\]", text)
    nrec_match = re.search(r"nrecords\s*=\s*\[\s*(\d+)\s*\]", text)

    dims = []
    if dims_match:
        nums = [int(x.strip()) for x in dims_match.group(1).split(",") if x.strip()]
        dims = [nums[i] for i in range(0, len(nums), 3)]

    fields = []
    if flds_match:
        fields = [s.strip().strip("'").strip()
                  for s in flds_match.group(1).split("'")
                  if s.strip().strip("'").strip()]

    nflds = int(nflds_match.group(1)) if nflds_match else len(fields)
    nrecs = int(nrec_match.group(1)) if nrec_match else nflds

    return {"dims": dims, "fields": fields, "nflds": nflds, "nrecords": nrecs}


def convert_one(data_path, meta, run_dir, Nx, Ny, Nr, nPx, nPy, deltaT, start_date):
    """Convert one binary diagnostics file to per-tile NetCDF."""
    _import_xr()
    from datetime import datetime, timedelta

    sNx = Nx // nPx
    sNy = Ny // nPy
    fields = meta["fields"]

    # Parse timestep from filename: state3D.0000000240.data
    basename = os.path.basename(data_path)
    prefix = basename.split(".")[0]
    iter_str = basename.split(".")[1]
    iter_num = int(iter_str)

    # Compute model time
    t0 = datetime.strptime(start_date, "%Y-%m-%d")
    model_time = t0 + timedelta(seconds=iter_num * deltaT)

    # Read the full binary file
    raw = np.fromfile(data_path, dtype=">f4")

    # Determine field sizes: 3D fields have Nr levels, 2D have 1
    # We detect by checking if nrecords == nflds (all same size) or nrecords > nflds
    recs_per_field = meta["nrecords"] // meta["nflds"]
    if recs_per_field > 1:
        # 3D fields with Nr levels
        rec_size = Nx * Ny * Nr
        is_3d = True
    else:
        # Could be 2D or mixed — check total size
        total_expected_3d = meta["nflds"] * Nx * Ny * Nr
        total_expected_2d = meta["nflds"] * Nx * Ny
        if raw.size == total_expected_3d:
            rec_size = Nx * Ny * Nr
            is_3d = True
        elif raw.size == total_expected_2d:
            rec_size = Nx * Ny
            is_3d = False
        else:
            # Mixed 2D/3D — use nrecords to figure it out
            rec_size = raw.size // meta["nrecords"]
            is_3d = (rec_size == Nx * Ny * Nr // meta["nflds"])  # rough guess
            # Fall back to per-field detection below
            pass

    # Find or create MNC output directory
    # Use the first existing mnc_ directory's naming convention
    mnc_dirs = sorted(glob.glob(os.path.join(run_dir, "mnc_*_0001/")))
    if mnc_dirs:
        mnc_prefix = os.path.basename(mnc_dirs[0].rstrip("/")).rsplit("_", 1)[0]
    else:
        mnc_prefix = "mnc_converted"

    # Read grid file to get tile info (X, Y coordinates per tile)
    # We need the tile suffix and X/Y offsets
    tile_info = {}
    for d in sorted(glob.glob(os.path.join(run_dir, "mnc_*_*/"))):
        grid_files = glob.glob(os.path.join(d, "grid.t*.nc"))
        if not grid_files:
            continue
        gf = grid_files[0]
        ds_g = _xr.open_dataset(gf)
        x0 = int(ds_g["X"].values[0])
        y0 = int(ds_g["Y"].values[0])
        ds_g.close()
        px = (x0 - 1) // sNx
        py = (y0 - 1) // sNy
        tile_suffix = os.path.basename(gf).replace("grid.", "").replace(".nc", "")
        dir_name = os.path.basename(d.rstrip("/"))
        tile_info[(py, px)] = {"dir": d, "tile": tile_suffix, "x0": x0, "y0": y0}

    if not tile_info:
        print(f"  No tile grid info found, skipping {basename}")
        return False

    # Parse fields from binary into global arrays
    global_fields = {}
    offset = 0
    for fname in fields:
        # Determine if this field is 3D or 2D
        # 3D: U, V, Theta, Salt, WVEL; 2D: ETAN
        if fname in ("ETAN", "EtaN", "ETAH", "oceFWflx", "TFLUX", "SFLUX",
                     "oceSflux", "oceQnet", "CH_QNET", "CH_EmP"):
            fld_size = Nx * Ny
            shape = (Ny, Nx)
            fld_3d = False
        else:
            fld_size = Nx * Ny * Nr
            shape = (Nr, Ny, Nx)
            fld_3d = True

        if offset + fld_size > raw.size:
            print(f"  Warning: not enough data for field {fname}, skipping rest")
            break
        global_fields[fname] = {"data": raw[offset:offset + fld_size].reshape(shape), "is_3d": fld_3d}
        offset += fld_size

    # Write per-tile NetCDF
    written = 0
    for (py, px), info in tile_info.items():
        j0 = py * sNy
        i0 = px * sNx

        nc_path = os.path.join(info["dir"], f"{prefix}.{iter_str}.{info['tile']}.nc")
        if os.path.exists(nc_path):
            continue  # already converted

        ds_vars = {}
        for fname, finfo in global_fields.items():
            arr = finfo["data"]
            if finfo["is_3d"]:
                tile_data = arr[:, j0:j0 + sNy, i0:i0 + sNx]
                ds_vars[fname] = (["T", f"Zmd{Nr:06d}", "Y", "X"],
                                  tile_data[np.newaxis, :, :, :])
            else:
                tile_data = arr[j0:j0 + sNy, i0:i0 + sNx]
                ds_vars[fname] = (["T", "Y", "X"],
                                  tile_data[np.newaxis, :, :])

        ds = _xr.Dataset(
            ds_vars,
            coords={
                "T": [np.datetime64(model_time)],
                "X": np.arange(i0 + 1, i0 + sNx + 1, dtype=float),
                "Y": np.arange(j0 + 1, j0 + sNy + 1, dtype=float),
            },
        )
        if any(f["is_3d"] for f in global_fields.values()):
            ds.coords[f"Zmd{Nr:06d}"] = np.arange(Nr, dtype=float)

        ds.to_netcdf(nc_path)
        ds.close()
        written += 1

    return written > 0


def find_unconverted(run_dir, prefixes=("state3D", "state2D", "Thermo")):
    """Find binary diagnostics files that haven't been converted yet."""
    results = []
    for prefix in prefixes:
        for meta_path in sorted(glob.glob(os.path.join(run_dir, f"{prefix}.*.meta"))):
            data_path = meta_path.replace(".meta", ".data")
            if not os.path.exists(data_path):
                continue
            iter_str = os.path.basename(meta_path).split(".")[1]
            # Check if any tile NetCDF exists for this timestep
            mnc_dirs = glob.glob(os.path.join(run_dir, "mnc_*_0001/"))
            if mnc_dirs:
                existing = glob.glob(os.path.join(mnc_dirs[0], f"{prefix}.{iter_str}.*.nc"))
                if existing:
                    continue
            results.append((data_path, prefix, iter_str))
    return results


def main():
    parser = argparse.ArgumentParser(description="Convert binary diagnostics to NetCDF")
    parser.add_argument("run_dir", help="Path to run directory")
    parser.add_argument("--poll", type=int, default=60, help="Poll interval (0 = run once)")
    parser.add_argument("--start-date", default="2002-07-01")
    parser.add_argument("--dt", type=float, default=360.0)
    args = parser.parse_args()

    Nx, Ny, Nr = 768, 424, 50
    nPx, nPy = 8, 8
    run_dir = os.path.abspath(args.run_dir)

    print(f"Watching: {run_dir}")
    print(f"Grid: {Nx}x{Ny}x{Nr}, MPI: {nPx}x{nPy}")

    while True:
        unconverted = find_unconverted(run_dir)
        if unconverted:
            for data_path, prefix, iter_str in unconverted:
                meta_path = data_path.replace(".data", ".meta")
                meta = read_meta(meta_path)
                print(f"Converting {prefix}.{iter_str} ({len(meta['fields'])} fields)...")
                try:
                    convert_one(data_path, meta, run_dir, Nx, Ny, Nr, nPx, nPy,
                                args.dt, args.start_date)
                except Exception as e:
                    print(f"  Error: {e}")

        if args.poll <= 0:
            break
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
