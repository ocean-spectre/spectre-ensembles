"""Animate ocean boundary condition (OBC) binary files.

For each (variable, boundary) pair produces one MP4:
  - 3D variables (U, V, T, S): pcolormesh of depth × boundary-position over time
  - Eta: line plot of boundary-position over time

Output goes to <simulation_directory>/animations/ocean_bcs/.
"""

import os
import yaml
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter

from spectre_utils import common

VARS = ["U", "V", "T", "S", "Eta"]
BOUNDARIES = ["south", "north", "west", "east"]

PHYSICAL_BOUNDS = {
    "U":   (-3.0,  3.0),
    "V":   (-3.0,  3.0),
    "T":   (-2.0, 35.0),
    "S":   ( 0.0, 42.0),
    "Eta": (-3.0,  3.0),
}

UNITS = {"U": "m/s", "V": "m/s", "T": "°C", "S": "PSU", "Eta": "m"}

CMAPS = {
    "U": "RdBu_r", "V": "RdBu_r", "T": "plasma", "S": "viridis", "Eta": "RdBu_r"
}


def animate_boundary(da, var, boundary, out_path, fps=4, dpi=100):
    """Animate one (var, boundary) DataArray as an MP4."""
    pos_dim = [d for d in da.dims if d not in ("time", "depth")][0]
    pos     = da.coords[pos_dim].values
    times   = da.coords["time"].values
    nt      = da.sizes["time"]
    xlabel  = "Longitude" if pos_dim == "lon" else "Latitude"

    lo, hi  = PHYSICAL_BOUNDS.get(var, (None, None))
    cmap    = CMAPS.get(var, "viridis")
    unit    = UNITS.get(var, "")

    is_3d = da.ndim == 3

    if is_3d:
        fig, ax = plt.subplots(figsize=(10, 5), dpi=dpi)
        depth  = da.coords["depth"].values
        frame0 = da.isel(time=0).values.astype(np.float32)
        pcm = ax.pcolormesh(pos, depth, frame0, shading="auto",
                            vmin=lo, vmax=hi, cmap=cmap)
        plt.colorbar(pcm, ax=ax, label=f"{var} [{unit}]")
        ax.invert_yaxis()
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Depth (m)")

        def update(i):
            pcm.set_array(da.isel(time=i).values.astype(np.float32))

    else:
        fig, ax = plt.subplots(figsize=(10, 3), dpi=dpi)
        frame0 = da.isel(time=0).values.astype(np.float32)
        (line,) = ax.plot(pos, frame0, color="steelblue", lw=0.8)
        if lo is not None:
            ax.set_ylim(lo - abs(lo) * 0.1, hi + abs(hi) * 0.1)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(f"{var} [{unit}]")
        ax.grid(True, alpha=0.3)

        def update(i):
            line.set_ydata(da.isel(time=i).values.astype(np.float32))

    title = ax.set_title(
        f"{var} — {boundary}  |  {np.datetime_as_string(times[0], unit='D')}"
    )

    writer = FFMpegWriter(fps=fps, bitrate=-1)
    with writer.saving(fig, out_path, dpi):
        writer.grab_frame()
        for i in range(1, nt):
            update(i)
            title.set_text(
                f"{var} — {boundary}  |  {np.datetime_as_string(times[i], unit='D')}"
            )
            writer.grab_frame()

    plt.close(fig)
    print(f"  Saved {out_path}")


def main():
    args = common.cli()

    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)

    simulation_directory = config["simulation_directory"]
    working_directory    = config["working_directory"]
    simulation_input_dir = os.path.join(simulation_directory, "input")

    animations_dir = os.path.join(simulation_directory, "animations", "ocean_bcs")
    os.makedirs(animations_dir, exist_ok=True)

    print("Loading OBC binary files...")
    data = common.load_obc_binaries(simulation_input_dir, working_directory, config)

    for var in VARS:
        for bnd in BOUNDARIES:
            key = (var, bnd)
            if key not in data:
                print(f"  Skipping {var}.{bnd} (not found)")
                continue
            out_path = os.path.join(animations_dir, f"{var}_{bnd}.mp4")
            print(f"Animating {var}.{bnd} -> {out_path}")
            animate_boundary(data[key], var, bnd, out_path, fps=4)

    print("Done.")


if __name__ == "__main__":
    main()
