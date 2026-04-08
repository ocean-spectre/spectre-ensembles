"""
plot_surface_fields.py
======================
Watch a simulation directory for MNC NetCDF diagnostics output across all
run subdirectories and render 2D surface field plots.

Usage:
    python plot_surface_fields.py <simulation_dir> [--poll 120]
"""

import os
import sys
import re
import time
import argparse
import glob
import numpy as np

_plt = None
_xr = None


def _import_mpl():
    global _plt
    if _plt is None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        _plt = plt


def _import_xr():
    global _xr
    if _xr is None:
        import xarray as xr
        _xr = xr


# ---------------------------------------------------------------------------
# Run discovery
# ---------------------------------------------------------------------------

def discover_runs(simulation_dir):
    runs = []
    for d in sorted(os.listdir(simulation_dir)):
        full = os.path.join(simulation_dir, d)
        if os.path.isdir(full) and os.path.exists(os.path.join(full, "STDOUT.0000")):
            runs.append(full)
    return runs


# ---------------------------------------------------------------------------
# MNC tile reader
# ---------------------------------------------------------------------------

def read_model_grid(horizgridfile, Nx, Ny):
    arr = np.fromfile(horizgridfile, dtype=">f8")
    fields = arr.reshape(16, Ny + 1, Nx + 1)
    return fields[0, :Ny, :Nx], fields[1, :Ny, :Nx]


def get_tile_layout(run_dir, nPx, nPy, sNx=96, sNy=53):
    _import_xr()
    layout = {}
    mnc_dirs = sorted(glob.glob(os.path.join(run_dir, "mnc_*_*/")))
    seen = set()
    for d in mnc_dirs:
        grid_files = glob.glob(os.path.join(d, "grid.t*.nc"))
        if not grid_files:
            continue
        gf = grid_files[0]
        ds = _xr.open_dataset(gf)
        x0 = int(ds["X"].values[0])
        y0 = int(ds["Y"].values[0])
        ds.close()
        tile_px = (x0 - 1) // sNx
        tile_py = (y0 - 1) // sNy
        tile_suffix = os.path.basename(gf).replace("grid.", "").replace(".nc", "")
        if (tile_py, tile_px) not in seen:
            layout[(tile_py, tile_px)] = {"dir": d, "tile": tile_suffix}
            seen.add((tile_py, tile_px))
    return layout


def stitch_field_2d(run_dir, file_prefix, timestep_str, var_name, layout,
                     nPx, nPy, sNx, sNy, k=None):
    _import_xr()
    Nx = sNx * nPx
    Ny = sNy * nPy
    global_field = np.full((Ny, Nx), np.nan, dtype=np.float32)

    for (py, px), info in layout.items():
        fname = os.path.join(info["dir"], f"{file_prefix}.{timestep_str}.{info['tile']}.nc")
        if not os.path.exists(fname):
            continue
        try:
            ds = _xr.open_dataset(fname)
        except Exception:
            continue
        if var_name not in ds:
            ds.close()
            continue
        data = ds[var_name]
        if k is not None:
            z_dims = [d for d in data.dims if d.startswith("Z")]
            if z_dims:
                data = data.isel({z_dims[0]: k})
        if "T" in data.dims:
            data = data.isel(T=-1)
        arr = data.values.squeeze()
        ds.close()

        j0 = py * sNy
        i0 = px * sNx
        ny_tile = min(arr.shape[-2], sNy)
        nx_tile = min(arr.shape[-1], sNx)
        global_field[j0:j0 + ny_tile, i0:i0 + nx_tile] = arr[:ny_tile, :nx_tile]

    return global_field


def find_diag_timesteps(run_dir, prefix="state3D", n_tiles=64):
    """Find timesteps where all tiles have been converted to NetCDF."""
    # Count how many tile directories exist
    mnc_dirs = glob.glob(os.path.join(run_dir, "mnc_*_*/"))
    if not mnc_dirs:
        return []
    n_dirs = len(mnc_dirs)

    # Find candidate timesteps from one tile dir
    candidates = set()
    for d in glob.glob(os.path.join(run_dir, "mnc_*_0001/")):
        for f in glob.glob(os.path.join(d, f"{prefix}.*.t*.nc")):
            m = re.search(rf"{prefix}\.(\d{{10}})\.t", f)
            if m:
                candidates.add(m.group(1))

    # Verify all tiles are present for each candidate
    ready = []
    for ts in sorted(candidates):
        count = 0
        for d in mnc_dirs:
            if glob.glob(os.path.join(d, f"{prefix}.{ts}.t*.nc")):
                count += 1
        if count >= n_dirs:
            ready.append(ts)
    return ready


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

FIELD_CONFIG = {
    "SST": {"label": "Sea Surface Temperature", "unit": "°C",
            "cmap": "RdYlBu_r", "vmin": 2, "vmax": 30},
    "SSS": {"label": "Sea Surface Salinity", "unit": "PSU",
            "cmap": "viridis", "vmin": 33, "vmax": 37},
    "SSH": {"label": "Sea Surface Height", "unit": "m",
            "cmap": "RdBu_r", "vmin": -1.5, "vmax": 1.5},
    "KE":  {"label": "Surface Kinetic Energy", "unit": "m²/s²",
            "cmap": "hot_r", "vmin": 0, "vmax": 0.5},
}


def plot_field(field_data, field_name, xC, yC, model_date, output_path):
    _import_mpl()
    cfg = FIELD_CONFIG[field_name]
    fig, ax = _plt.subplots(1, 1, figsize=(12, 6))
    masked = np.ma.masked_where((field_data == 0) | np.isnan(field_data), field_data)
    im = ax.pcolormesh(xC, yC, masked, cmap=cfg["cmap"],
                       vmin=cfg["vmin"], vmax=cfg["vmax"], shading="auto")
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label(cfg["unit"], fontsize=10)
    ax.set_title(f'{cfg["label"]} — {model_date}', fontsize=13)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    _plt.close(fig)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def process_run(run_dir, xC, yC, plotted_cache, nPx, nPy, sNx, sNy, deltaT, start_date):
    """Process one run directory. Returns number of new plots."""
    from datetime import datetime, timedelta

    Nx = sNx * nPx
    Ny = sNy * nPy
    t0 = datetime.strptime(start_date, "%Y-%m-%d")
    plots_dir = os.path.join(run_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)

    run_name = os.path.basename(run_dir)
    if run_name not in plotted_cache:
        plotted_cache[run_name] = set()
    plotted = plotted_cache[run_name]

    # Get or build tile layout
    layout = get_tile_layout(run_dir, nPx, nPy, sNx, sNy)
    if not layout:
        return 0

    timesteps = find_diag_timesteps(run_dir, "state3D")
    new_count = 0

    for ts in timesteps:
        if ts in plotted:
            continue

        iter_num = int(ts)
        model_seconds = iter_num * deltaT
        model_date = (t0 + timedelta(seconds=model_seconds)).strftime("%Y-%m-%d")

        # Minimum fraction of valid (non-zero, non-NaN) ocean points
        # to consider the stitched field complete. If below this, skip
        # and retry on the next poll cycle.
        MIN_VALID_FRAC = 0.5
        n_total = Nx * Ny
        skip_ts = False

        # SST, SSS
        for var, field_name, k in [("THETA", "SST", 0), ("SALT", "SSS", 0)]:
            out = os.path.join(plots_dir, f"{field_name}_{ts}.png")
            if not os.path.exists(out):
                data = stitch_field_2d(run_dir, "state3D", ts, var, layout,
                                        nPx, nPy, sNx, sNy, k=k)
                n_valid = np.sum((data != 0) & ~np.isnan(data))
                if n_valid < n_total * MIN_VALID_FRAC:
                    print(f"  [{run_name}] {field_name} {ts}: only {n_valid}/{n_total} valid — skipping, will retry")
                    skip_ts = True
                    break
                try:
                    plot_field(data, field_name, xC, yC, model_date, out)
                    new_count += 1
                except Exception as e:
                    print(f"  [{run_name}] Error plotting {field_name}: {e}")

        if skip_ts:
            continue  # don't mark as plotted — retry next cycle

        # KE
        out = os.path.join(plots_dir, f"KE_{ts}.png")
        if not os.path.exists(out):
            u = stitch_field_2d(run_dir, "state3D", ts, "UVEL", layout,
                                nPx, nPy, sNx, sNy, k=0)
            v = stitch_field_2d(run_dir, "state3D", ts, "VVEL", layout,
                                nPx, nPy, sNx, sNy, k=0)
            ke = 0.5 * (u ** 2 + v ** 2)
            try:
                plot_field(ke, "KE", xC, yC, model_date, out)
                new_count += 1
            except Exception as e:
                print(f"  [{run_name}] Error plotting KE: {e}")

        # SSH
        ts2d = find_diag_timesteps(run_dir, "state2D")
        if ts in ts2d:
            out = os.path.join(plots_dir, f"SSH_{ts}.png")
            if not os.path.exists(out):
                etan = stitch_field_2d(run_dir, "state2D", ts, "ETAN", layout,
                                       nPx, nPy, sNx, sNy)
                try:
                    plot_field(etan, "SSH", xC, yC, model_date, out)
                    new_count += 1
                except Exception as e:
                    print(f"  [{run_name}] Error plotting SSH: {e}")

        # Only mark as plotted if all expected files exist
        expected = [f"{fn}_{ts}.png" for fn in ["SST", "SSS", "KE", "SSH"]]
        if all(os.path.exists(os.path.join(plots_dir, e)) for e in expected):
            plotted.add(ts)

    return new_count


def main():
    parser = argparse.ArgumentParser(description="Plot MITgcm surface fields")
    parser.add_argument("simulation_dir", help="Path to simulation directory")
    parser.add_argument("--poll", type=int, default=120)
    parser.add_argument("--start-date", default="2002-07-01")
    parser.add_argument("--dt", type=float, default=360.0)
    args = parser.parse_args()

    Nx, Ny, Nz = 768, 424, 50
    nPx, nPy = 8, 8
    sNx, sNy = Nx // nPx, Ny // nPy
    simulation_dir = os.path.abspath(args.simulation_dir)

    # Read model grid
    horizgridfile = os.path.join(simulation_dir, "input", "horizgridfile.bin")
    xC, yC = read_model_grid(horizgridfile, Nx, Ny)
    print(f"Grid: {Ny}x{Nx}, lon [{xC.min():.1f},{xC.max():.1f}], lat [{yC.min():.1f},{yC.max():.1f}]")
    print(f"Watching: {simulation_dir}")

    plotted_cache = {}  # run_name → set of plotted timesteps

    while True:
        for run_dir in discover_runs(simulation_dir):
            run_name = os.path.basename(run_dir)
            n = process_run(run_dir, xC, yC, plotted_cache, nPx, nPy, sNx, sNy,
                           args.dt, args.start_date)
            if n > 0:
                print(f"[{run_name}] Plotted {n} new images")

        if args.poll <= 0:
            break
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
