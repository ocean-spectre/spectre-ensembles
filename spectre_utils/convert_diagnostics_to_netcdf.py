"""
convert_diagnostics_to_netcdf.py
================================
Watch a simulation directory for binary diagnostics output (.data/.meta)
across all run subdirectories and convert to per-tile NetCDF files.

Usage:
    python convert_diagnostics_to_netcdf.py <simulation_dir> [--poll 60]
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


def discover_runs(simulation_dir):
    """Find subdirectories containing STDOUT.0000."""
    runs = []
    for d in sorted(os.listdir(simulation_dir)):
        full = os.path.join(simulation_dir, d)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, "STDOUT.0000")):
            runs.append(full)
    return runs


def read_meta(meta_path):
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


# 2D field names (everything else assumed 3D)
FIELDS_2D = {"ETAN", "EtaN", "ETAH", "dEtaHdt", "oceFWflx", "TFLUX", "SFLUX",
             "oceSflux", "oceQnet", "CH_QNET", "CH_EmP"}


def convert_one(data_path, meta, run_dir, Nx, Ny, Nr, nPx, nPy, deltaT, start_date):
    _import_xr()
    from datetime import datetime, timedelta

    sNx = Nx // nPx
    sNy = Ny // nPy
    fields = meta["fields"]
    basename = os.path.basename(data_path)
    prefix = basename.split(".")[0]
    iter_str = basename.split(".")[1]
    iter_num = int(iter_str)
    t0 = datetime.strptime(start_date, "%Y-%m-%d")
    model_time = t0 + timedelta(seconds=iter_num * deltaT)

    raw = np.fromfile(data_path, dtype=">f4")

    # Parse fields
    global_fields = {}
    offset = 0
    for fname in fields:
        if fname in FIELDS_2D:
            fld_size = Nx * Ny
            shape = (Ny, Nx)
            fld_3d = False
        else:
            fld_size = Nx * Ny * Nr
            shape = (Nr, Ny, Nx)
            fld_3d = True
        if offset + fld_size > raw.size:
            break
        global_fields[fname] = {"data": raw[offset:offset + fld_size].reshape(shape), "is_3d": fld_3d}
        offset += fld_size

    # Validate: the first field should have a reasonable number of non-zero values
    # (at least 30% — ocean covers ~80% of the domain). If mostly zeros, the
    # binary was likely read before MITgcm finished flushing to disk.
    first_field = list(global_fields.values())[0]["data"] if global_fields else None
    if first_field is not None:
        nonzero_frac = np.count_nonzero(first_field) / first_field.size
        if nonzero_frac < 0.3:
            print(f"  SKIP {basename}: only {nonzero_frac:.1%} non-zero — likely incomplete flush")
            return False

    # Get tile layout from grid files
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
        if (py, px) not in tile_info:
            tile_info[(py, px)] = {"dir": d, "tile": tile_suffix}

    if not tile_info:
        return False

    written = 0
    for (py, px), info in tile_info.items():
        j0 = py * sNy
        i0 = px * sNx
        nc_path = os.path.join(info["dir"], f"{prefix}.{iter_str}.{info['tile']}.nc")
        if os.path.exists(nc_path):
            continue

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

        ds = _xr.Dataset(ds_vars, coords={
            "T": [np.datetime64(model_time)],
            "X": np.arange(i0 + 1, i0 + sNx + 1, dtype=float),
            "Y": np.arange(j0 + 1, j0 + sNy + 1, dtype=float),
        })
        if any(f["is_3d"] for f in global_fields.values()):
            ds.coords[f"Zmd{Nr:06d}"] = np.arange(Nr, dtype=float)

        tmp_path = nc_path + ".tmp"
        ds.to_netcdf(tmp_path)
        ds.close()
        os.replace(tmp_path, nc_path)
        written += 1

    return written > 0


def find_unconverted(run_dir, prefixes=("state3D", "state2D", "Thermo"), min_age_s=120):
    """Find binary diagnostics files ready for conversion.

    Only returns files older than min_age_s seconds to ensure MITgcm
    has finished writing and flushing to disk.
    """
    import time as _time
    now = _time.time()
    results = []
    for prefix in prefixes:
        for meta_path in sorted(glob.glob(os.path.join(run_dir, f"{prefix}.*.meta"))):
            data_path = meta_path.replace(".meta", ".data")
            if not os.path.exists(data_path):
                continue
            # Skip files that are too recent (may still be written)
            if now - os.path.getmtime(data_path) < min_age_s:
                continue
            iter_str = os.path.basename(meta_path).split(".")[1]
            mnc_dirs = glob.glob(os.path.join(run_dir, "mnc_*_0001/"))
            if mnc_dirs:
                existing = glob.glob(os.path.join(mnc_dirs[0], f"{prefix}.{iter_str}.*.nc"))
                if existing:
                    continue
            results.append((data_path, prefix, iter_str))
    return results


def main():
    parser = argparse.ArgumentParser(description="Convert binary diagnostics to NetCDF")
    parser.add_argument("simulation_dir", help="Path to simulation directory")
    parser.add_argument("--poll", type=int, default=60)
    parser.add_argument("--start-date", default="2002-07-01")
    parser.add_argument("--dt", type=float, default=360.0)
    args = parser.parse_args()

    Nx, Ny, Nr = 768, 424, 50
    nPx, nPy = 8, 8
    simulation_dir = os.path.abspath(args.simulation_dir)
    print(f"Watching simulation directory: {simulation_dir}")

    while True:
        for run_dir in discover_runs(simulation_dir):
            unconverted = find_unconverted(run_dir)
            if unconverted:
                run_name = os.path.basename(run_dir)
                for data_path, prefix, iter_str in unconverted:
                    meta_path = data_path.replace(".data", ".meta")
                    meta = read_meta(meta_path)
                    print(f"[{run_name}] Converting {prefix}.{iter_str}...")
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
