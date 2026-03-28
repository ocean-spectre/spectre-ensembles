"""
plot_surface_fields.py
======================
Watch MITgcm diagnostics output (MNC NetCDF tiles) and render 2D surface
field plots.

Reads per-tile NetCDF files from the diagnostics package, stitches tiles,
extracts surface-level fields, and saves PNG plots.

Usage:
    python plot_surface_fields.py <run_dir> [--poll 60] [--plots-dir plots]

Fields plotted:
    SST  — Sea Surface Temperature (THETA, k=0)
    SSS  — Sea Surface Salinity (SALT, k=0)
    SSH  — Sea Surface Height (ETAN)
    KE   — Surface Kinetic Energy (0.5*(UVEL² + VVEL²), k=0)
"""

import os
import sys
import re
import time
import argparse
import glob
import numpy as np

# Lazy imports for heavy libraries
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
# MNC tile reader
# ---------------------------------------------------------------------------

def read_model_grid(horizgridfile, Nx, Ny):
    """Read xC, yC from the curvilinear horizgridfile."""
    arr = np.fromfile(horizgridfile, dtype=">f8")
    fields = arr.reshape(16, Ny + 1, Nx + 1)
    return fields[0, :Ny, :Nx], fields[1, :Ny, :Nx]


def get_tile_layout(run_dir, nPx, nPy, sNx=96, sNy=53):
    """Build a mapping from (tile_py, tile_px) → MNC directory + tile file suffix.

    Uses the X/Y coordinate indices in each tile's grid file to determine
    the tile's position in the global grid, avoiding assumptions about
    MNC directory numbering.
    """
    _import_xr()
    layout = {}
    mnc_dirs = sorted(glob.glob(os.path.join(run_dir, "mnc_*_*/")))
    seen_positions = set()
    for d in mnc_dirs:
        grid_files = glob.glob(os.path.join(d, "grid.t*.nc"))
        if not grid_files:
            continue
        gf = grid_files[0]
        ds = _xr.open_dataset(gf)
        # Global index offsets from the X/Y coordinates
        x0 = int(ds["X"].values[0])
        y0 = int(ds["Y"].values[0])
        ds.close()
        tile_px = (x0 - 1) // sNx
        tile_py = (y0 - 1) // sNy
        tile_suffix = os.path.basename(gf).replace("grid.", "").replace(".nc", "")
        if (tile_py, tile_px) not in seen_positions:
            layout[(tile_py, tile_px)] = {"dir": d, "tile": tile_suffix}
            seen_positions.add((tile_py, tile_px))
    return layout


def stitch_field_2d(run_dir, file_prefix, timestep_str, var_name, layout,
                     nPx, nPy, sNx, sNy, k=None):
    """Read a variable from per-tile NetCDF and stitch into a global 2D array."""
    _import_xr()
    Nx = sNx * nPx
    Ny = sNy * nPy
    global_field = np.full((Ny, Nx), np.nan, dtype=np.float32)

    for (py, px), info in layout.items():
        fname = os.path.join(info["dir"], f"{file_prefix}.{timestep_str}.{info['tile']}.nc")
        if not os.path.exists(fname):
            continue
        ds = _xr.open_dataset(fname)
        if var_name not in ds:
            ds.close()
            continue
        data = ds[var_name]
        # Select surface level — Z dim name varies (e.g. Zmd000050, Z, Zl)
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
        # Trim staggered grid points (Xp1/Yp1) and halos to tile size
        ny_tile = min(arr.shape[-2], sNy)
        nx_tile = min(arr.shape[-1], sNx)
        global_field[j0:j0 + ny_tile, i0:i0 + nx_tile] = arr[:ny_tile, :nx_tile]

    return global_field


def find_diag_timesteps(run_dir, prefix="state3D"):
    """Find all timestep strings for a diagnostics file prefix."""
    timesteps = set()
    for d in glob.glob(os.path.join(run_dir, "mnc_*_0001/")):
        for f in glob.glob(os.path.join(d, f"{prefix}.*.t*.nc")):
            m = re.search(rf"{prefix}\.(\d{{10}})\.t", f)
            if m:
                timesteps.add(m.group(1))
    return sorted(timesteps)


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
    """Render a single 2D field to PNG."""
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

def main():
    parser = argparse.ArgumentParser(description="Plot MITgcm surface fields")
    parser.add_argument("run_dir", help="Path to run directory")
    parser.add_argument("--plots-dir", default=None,
                        help="Output directory for plots (default: run_dir/plots)")
    parser.add_argument("--poll", type=int, default=60,
                        help="Poll interval in seconds (0 = run once)")
    parser.add_argument("--start-date", default="2002-07-01",
                        help="Simulation start date")
    parser.add_argument("--dt", type=float, default=360.0,
                        help="Model timestep in seconds")
    args = parser.parse_args()

    from datetime import datetime, timedelta

    Nx, Ny, Nz = 768, 424, 50
    nPx, nPy = 8, 8
    sNx, sNy = Nx // nPx, Ny // nPy  # 96, 53
    run_dir = os.path.abspath(args.run_dir)
    plots_dir = args.plots_dir or os.path.join(run_dir, "plots")
    os.makedirs(plots_dir, exist_ok=True)
    t0 = datetime.strptime(args.start_date, "%Y-%m-%d")

    # Read model grid for plotting coordinates
    sim_dir = os.path.dirname(run_dir)
    horizgridfile = os.path.join(sim_dir, "input", "horizgridfile.bin")
    xC, yC = read_model_grid(horizgridfile, Nx, Ny)
    print(f"Grid: {Ny}x{Nx}, lon [{xC.min():.1f},{xC.max():.1f}], lat [{yC.min():.1f},{yC.max():.1f}]")

    # Discover tile layout once MNC directories exist
    layout = None
    plotted = set()

    while True:
        # Build layout on first pass or if empty
        if layout is None or len(layout) == 0:
            layout = get_tile_layout(run_dir, nPx, nPy)
            if not layout:
                if args.poll <= 0:
                    print("No MNC directories found.")
                    break
                print("Waiting for MNC directories...")
                time.sleep(args.poll)
                continue
            print(f"Found {len(layout)} tiles")

        timesteps = find_diag_timesteps(run_dir, "state3D")
        new_count = 0

        for ts in timesteps:
            if ts in plotted:
                continue

            iter_num = int(ts)
            model_seconds = iter_num * args.dt
            model_date = (t0 + timedelta(seconds=model_seconds)).strftime("%Y-%m-%d")

            print(f"Plotting timestep {ts} ({model_date})...")

            # SST, SSS, KE from state3D
            for var, field_name, k in [("THETA", "SST", 0), ("SALT", "SSS", 0)]:
                data = stitch_field_2d(run_dir, "state3D", ts, var, layout,
                                        nPx, nPy, sNx, sNy, k=k)
                out = os.path.join(plots_dir, f"{field_name}_{ts}.png")
                try:
                    plot_field(data, field_name, xC, yC, model_date, out)
                    new_count += 1
                except Exception as e:
                    print(f"  Error plotting {field_name}: {e}")

            # KE from UVEL + VVEL
            u = stitch_field_2d(run_dir, "state3D", ts, "UVEL", layout,
                                nPx, nPy, sNx, sNy, k=0)
            v = stitch_field_2d(run_dir, "state3D", ts, "VVEL", layout,
                                nPx, nPy, sNx, sNy, k=0)
            ke = 0.5 * (u ** 2 + v ** 2)
            out = os.path.join(plots_dir, f"KE_{ts}.png")
            try:
                plot_field(ke, "KE", xC, yC, model_date, out)
                new_count += 1
            except Exception as e:
                print(f"  Error plotting KE: {e}")

            # SSH from state2D
            ts2d = find_diag_timesteps(run_dir, "state2D")
            if ts in ts2d:
                etan = stitch_field_2d(run_dir, "state2D", ts, "ETAN", layout,
                                       nPx, nPy, sNx, sNy)
                out = os.path.join(plots_dir, f"SSH_{ts}.png")
                try:
                    plot_field(etan, "SSH", xC, yC, model_date, out)
                    new_count += 1
                except Exception as e:
                    print(f"  Error plotting SSH: {e}")

            plotted.add(ts)

        if new_count > 0:
            print(f"  Plotted {new_count} new images")

        if args.poll <= 0:
            break
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
