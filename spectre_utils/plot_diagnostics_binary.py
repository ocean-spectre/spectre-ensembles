#!/usr/bin/env python3
"""
plot_diagnostics_binary.py
==========================
Sidecar plotter for MITgcm binary diagnostics output.

Watches an experiment directory (e.g. repeat-year-50/) for new state3D/state2D
binary files and renders surface field plots (SST, SSS, SSH, KE) into each
run's plots/ subdirectory.

Designed to run on the login node alongside SLURM jobs.

Usage:
    nohup uv run python spectre_utils/plot_diagnostics_binary.py \
        simulations/glorysv12-curvilinear repeat-year-50 \
        --poll 120 &

    # Or watch a single run:
    uv run python spectre_utils/plot_diagnostics_binary.py \
        simulations/glorysv12-curvilinear repeat-year-50 --run 001 --poll 0
"""

import argparse
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

_plt = None


def _import_mpl():
    global _plt
    if _plt is None:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        _plt = plt


# ---------------------------------------------------------------------------
# Grid reader
# ---------------------------------------------------------------------------

def read_model_grid(horizgridfile, Nx, Ny):
    """Read curvilinear grid coordinates from horizgridfile.bin."""
    arr = np.fromfile(horizgridfile, dtype=">f8")
    fields = arr.reshape(16, Ny + 1, Nx + 1)
    return fields[0, :Ny, :Nx], fields[1, :Ny, :Nx]  # xC, yC


# ---------------------------------------------------------------------------
# Binary diagnostics reader
# ---------------------------------------------------------------------------

def parse_diag_meta(meta_path):
    """Parse a MITgcm diagnostics .meta file."""
    text = Path(meta_path).read_text()

    dim_match = re.search(r"dimList\s*=\s*\[\s*([\d\s,]+)\]", text)
    dims = [int(x) for x in dim_match.group(1).replace(",", " ").split()]
    ndims = len(dims) // 3
    nx, ny = dims[0], dims[3]
    nz = dims[6] if ndims >= 3 else 1

    prec_match = re.search(r"dataprec\s*=\s*\[\s*'(\w+)'\s*\]", text)
    dtype = np.dtype(">f8") if prec_match and "64" in prec_match.group(1) else np.dtype(">f4")

    nrec_match = re.search(r"nrecords\s*=\s*\[\s*(\d+)\s*\]", text)
    nrecords = int(nrec_match.group(1))

    fld_match = re.search(r"fldList\s*=\s*\{([^}]+)\}", text)
    fields = re.findall(r"'(\w+)\s*'", fld_match.group(1)) if fld_match else []

    return {
        "nx": nx, "ny": ny, "nz": nz, "ndims": ndims,
        "dtype": dtype, "nrecords": nrecords, "fields": fields,
    }


def read_surface_field(data_path, meta, field_name):
    """Read the surface (k=0) slice of a named field from binary diagnostics."""
    if field_name not in meta["fields"]:
        return None

    nx, ny, nz = meta["nx"], meta["ny"], meta["nz"]
    dtype = meta["dtype"]
    rec_size = nx * ny
    field_idx = meta["fields"].index(field_name)

    if meta["ndims"] == 3:
        # 3D file: each field has nz levels
        offset = field_idx * nz * rec_size
    else:
        # 2D file: each field is one record
        offset = field_idx * rec_size

    data = np.fromfile(data_path, dtype=dtype, count=rec_size, offset=offset * np.dtype(dtype).itemsize)
    return data.reshape(ny, nx)


# ---------------------------------------------------------------------------
# Run discovery
# ---------------------------------------------------------------------------

def discover_experiment_runs(simulation_dir, experiment):
    """Find run subdirectories under experiment/ that have diagnostic output."""
    exp_dir = os.path.join(simulation_dir, experiment)
    if not os.path.isdir(exp_dir):
        return []
    runs = []
    for d in sorted(os.listdir(exp_dir)):
        full = os.path.join(exp_dir, d)
        if os.path.isdir(full):
            runs.append(d)
    return runs


def find_diag_timesteps(run_dir, prefix="state3D"):
    """Find timestep suffixes for which both .data and .meta exist."""
    timesteps = set()
    for f in Path(run_dir).glob(f"{prefix}.*.data"):
        m = re.search(rf"{prefix}\.(\d{{10}})\.data", f.name)
        if m:
            ts = m.group(1)
            meta = f.with_suffix(".meta")
            if meta.exists():
                timesteps.add(ts)
    return sorted(timesteps)


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

FIELD_CONFIG = {
    "SST": {"label": "Sea Surface Temperature", "unit": "\u00b0C",
            "cmap": "RdYlBu_r", "vmin": 2, "vmax": 30},
    "SSS": {"label": "Sea Surface Salinity", "unit": "PSU",
            "cmap": "viridis", "vmin": 33, "vmax": 37},
    "SSH": {"label": "Sea Surface Height", "unit": "m",
            "cmap": "RdBu_r", "vmin": -1.5, "vmax": 1.5},
    "KE":  {"label": "Surface Kinetic Energy", "unit": "m\u00b2/s\u00b2",
            "cmap": "hot_r", "vmin": 0, "vmax": 0.5},
}


def plot_field(field_data, field_name, xC, yC, title_extra, output_path):
    _import_mpl()
    cfg = FIELD_CONFIG[field_name]
    fig, ax = _plt.subplots(1, 1, figsize=(12, 6))
    masked = np.ma.masked_where(
        (field_data == 0) | np.isnan(field_data) | (field_data <= -999), field_data
    )
    im = ax.pcolormesh(xC, yC, masked, cmap=cfg["cmap"],
                       vmin=cfg["vmin"], vmax=cfg["vmax"], shading="auto")
    cb = fig.colorbar(im, ax=ax, shrink=0.8, pad=0.02)
    cb.set_label(cfg["unit"], fontsize=10)
    ax.set_title(f'{cfg["label"]} \u2014 {title_extra}', fontsize=13)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(output_path, dpi=120, bbox_inches="tight")
    _plt.close(fig)


# ---------------------------------------------------------------------------
# Processing
# ---------------------------------------------------------------------------

def process_run(run_dir, run_name, xC, yC, plotted, deltaT, start_date, nx, ny):
    """Process one run directory. Returns number of new plots created."""
    t0 = datetime.strptime(start_date, "%Y-%m-%d")
    plots_dir = os.path.join(run_dir, "plots")
    new_count = 0

    # Find available timesteps
    ts_3d = find_diag_timesteps(run_dir, "state3D")
    ts_2d = find_diag_timesteps(run_dir, "state2D")

    for ts in ts_3d:
        if ts in plotted:
            continue

        iter_num = int(ts)
        model_date = (t0 + timedelta(seconds=iter_num * deltaT)).strftime("%Y-%m-%d")
        title = f"{run_name} \u2014 {model_date}"

        data_path = os.path.join(run_dir, f"state3D.{ts}.data")
        meta_path = os.path.join(run_dir, f"state3D.{ts}.meta")
        meta = parse_diag_meta(meta_path)

        os.makedirs(plots_dir, exist_ok=True)

        try:
            # SST
            sst = read_surface_field(data_path, meta, "THETA")
            if sst is not None:
                out = os.path.join(plots_dir, f"SST_{ts}.png")
                if not os.path.exists(out):
                    plot_field(sst, "SST", xC, yC, title, out)
                    new_count += 1

            # SSS
            sss = read_surface_field(data_path, meta, "SALT")
            if sss is not None:
                out = os.path.join(plots_dir, f"SSS_{ts}.png")
                if not os.path.exists(out):
                    plot_field(sss, "SSS", xC, yC, title, out)
                    new_count += 1

            # KE
            u = read_surface_field(data_path, meta, "UVEL")
            v = read_surface_field(data_path, meta, "VVEL")
            if u is not None and v is not None:
                ke = 0.5 * (u ** 2 + v ** 2)
                out = os.path.join(plots_dir, f"KE_{ts}.png")
                if not os.path.exists(out):
                    plot_field(ke, "KE", xC, yC, title, out)
                    new_count += 1

        except Exception as e:
            print(f"  [{run_name}] Error processing state3D {ts}: {e}")
            continue

        # SSH from state2D
        if ts in ts_2d:
            try:
                data2d_path = os.path.join(run_dir, f"state2D.{ts}.data")
                meta2d = parse_diag_meta(os.path.join(run_dir, f"state2D.{ts}.meta"))
                etan = read_surface_field(data2d_path, meta2d, "ETAN")
                if etan is not None:
                    out = os.path.join(plots_dir, f"SSH_{ts}.png")
                    if not os.path.exists(out):
                        plot_field(etan, "SSH", xC, yC, title, out)
                        new_count += 1
            except Exception as e:
                print(f"  [{run_name}] Error processing state2D {ts}: {e}")

        plotted.add(ts)

    return new_count


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Sidecar plotter for MITgcm binary diagnostics"
    )
    parser.add_argument("simulation_dir",
                        help="Path to simulation directory (e.g. simulations/glorysv12-curvilinear)")
    parser.add_argument("experiment",
                        help="Experiment subdirectory (e.g. repeat-year-50)")
    parser.add_argument("--run", default=None,
                        help="Watch a single run (e.g. 001) instead of all runs")
    parser.add_argument("--poll", type=int, default=120,
                        help="Seconds between polls (0 = single pass, no loop)")
    parser.add_argument("--start-date", default="2002-07-01")
    parser.add_argument("--dt", type=float, default=360.0, help="Model timestep in seconds")
    args = parser.parse_args()

    Nx, Ny = 768, 424
    simulation_dir = os.path.abspath(args.simulation_dir)
    exp_dir = os.path.join(simulation_dir, args.experiment)

    horizgridfile = os.path.join(simulation_dir, "input", "horizgridfile.bin")
    xC, yC = read_model_grid(horizgridfile, Nx, Ny)
    print(f"Grid loaded: {Ny}x{Nx}, lon [{xC.min():.1f},{xC.max():.1f}], lat [{yC.min():.1f},{yC.max():.1f}]")
    print(f"Watching: {exp_dir}")
    if args.run:
        print(f"Single run: {args.run}")

    plotted_cache = {}  # run_name → set of plotted timesteps

    while True:
        if args.run:
            runs = [args.run]
        else:
            runs = discover_experiment_runs(simulation_dir, args.experiment)

        for run_name in runs:
            run_dir = os.path.join(exp_dir, run_name)
            if not os.path.isdir(run_dir):
                continue

            if run_name not in plotted_cache:
                plotted_cache[run_name] = set()

            n = process_run(run_dir, f"{args.experiment}/{run_name}",
                           xC, yC, plotted_cache[run_name],
                           args.dt, args.start_date, Nx, Ny)
            if n > 0:
                print(f"[{args.experiment}/{run_name}] Plotted {n} new images")

        if args.poll <= 0:
            break
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
