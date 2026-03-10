import os
import yaml
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter
from datetime import datetime

from spectre_utils import common


def animate_variable(
    ds: xr.Dataset,
    var: str,
    out_path: str = "animation.mp4",
    fps: int = 10,
    cmap: str = "viridis",
    vmin: float | None = None,
    vmax: float | None = None,
    robust: bool = True,
    dpi: int = 100,
    title: str | None = None,
):
    """Create an MP4 animation of ds[var] over the 'valid_time' dimension."""
    da = ds[var]
    if "valid_time" not in da.dims:
        raise ValueError(f"{var} must have a 'valid_time' dimension.")

    if vmin is None or vmax is None:
        if robust:
            q = da.isel(valid_time=slice(0, max(1, min(5, da.sizes["valid_time"]))))
            lo, hi = q.quantile([0.02, 0.98], dim=("valid_time", "latitude", "longitude")).compute().values
            vmin = lo if vmin is None else vmin
            vmax = hi if vmax is None else vmax
        else:
            vmin = da.min().compute().item() if vmin is None else vmin
            vmax = da.max().compute().item() if vmax is None else vmax
        if vmin == vmax:
            eps = 1e-6 if vmin == 0 else abs(vmin) * 1e-3
            vmin, vmax = vmin - eps, vmax + eps

    lat = da.coords.get("latitude")
    lon = da.coords.get("longitude")
    if lat is None or lon is None:
        raise ValueError("Expected 'latitude' and 'longitude' coordinates.")

    if lat.ndim == 1 and lon.ndim == 1:
        X, Y = np.meshgrid(lon.values, lat.values)
    else:
        X, Y = lon.values, lat.values

    fig, ax = plt.subplots(figsize=(8, 5), dpi=dpi)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    frame0 = da.isel(valid_time=0).compute()
    mappable = ax.pcolormesh(X, Y, frame0, shading="auto", vmin=vmin, vmax=vmax, cmap=cmap)

    cbar = fig.colorbar(mappable, ax=ax, pad=0.02)
    var_units = da.attrs.get("units", "")
    cbar.set_label(f"{var} [{var_units}]" if var_units else var)

    ttl_prefix = title if title is not None else f"{var} {('['+var_units+']') if var_units else ''}".strip()
    time_values = ds["valid_time"].values

    def set_title(i):
        tval = (
            np.datetime_as_string(time_values[i], unit="h")
            if np.issubdtype(time_values.dtype, np.datetime64)
            else str(time_values[i])
        )
        ax.set_title(f"{ttl_prefix}\n{tval}")

    set_title(0)

    writer = FFMpegWriter(fps=fps, metadata={"artist": "spectre"}, bitrate=-1)
    with writer.saving(fig, out_path, dpi):
        writer.grab_frame()
        for i in range(1, da.sizes["valid_time"]):
            mappable.set_array(da.isel(valid_time=i).compute())
            set_title(i)
            writer.grab_frame()

    plt.close(fig)
    print(f"  Saved {out_path}")
    return out_path


def main():
    args = common.cli()

    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)

    working_directory = config["working_directory"]
    simulation_directory = config["simulation_directory"]
    years = config["atmosphere"]["years"]
    atm_vars = config["atmosphere"]["variables"]
    computed_vars = config["atmosphere"].get("computed_variables", [])
    prefix = config["atmosphere"]["prefix"]

    t1 = datetime.strptime(config["domain"]["time"]["start"], "%Y-%m-%d")
    t2 = datetime.strptime(config["domain"]["time"]["end"], "%Y-%m-%d")

    animations_dir = os.path.join(simulation_directory, "animations", "atmosphere")
    os.makedirs(animations_dir, exist_ok=True)
    simulation_input_dir = os.path.join(simulation_directory, "input")

    # Collect all variable names to animate (configured + computed), deduplicated
    seen = set()
    to_animate = []
    for var in atm_vars:
        n = var["mitgcm_name"]
        if n not in seen:
            seen.add(n)
            to_animate.append(n)
    for cv in computed_vars:
        n = cv["mitgcm_name"]
        if n not in seen:
            seen.add(n)
            to_animate.append(n)

    print("Loading EXF binary files...")
    ds = common.load_exf_binaries(
        simulation_input_dir, to_animate, working_directory, prefix, years, atm_vars, t1, t2
    )

    for name in to_animate:
        if name not in ds:
            print(f"  Skipping {name} (not in dataset)")
            continue
        out_path = os.path.join(animations_dir, f"{name}.mp4")
        print(f"Animating {name} -> {out_path}")
        animate_variable(ds, name, out_path=out_path, fps=8, cmap="plasma")

    print("Done.")


if __name__ == "__main__":
    main()
