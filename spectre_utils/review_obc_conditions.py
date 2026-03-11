"""
QC review of ocean boundary condition (OBC) binary files.

Loads the written boundary condition files, runs physical range / consistency
checks, verifies binary file sizes, and writes a Markdown report plus
diagnostic figures to:

    <simulation_directory>/review/ocean_bcs/
        report.md
        sections_{boundary}.png  -- time-mean cross-section per boundary
        timeseries.png           -- boundary-mean time series per variable
        depth_profiles.png       -- mean depth profiles of T, S, U, V
"""

import os
import sys
import yaml
import numpy as np
import xarray as xr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from datetime import datetime, timezone

from spectre_utils import common

VARS = ["U", "V", "T", "S", "Eta"]
BOUNDARIES = ["south", "north", "west", "east"]

PHYSICAL_BOUNDS = {
    "U":   (-3.0,  3.0),   # m/s
    "V":   (-3.0,  3.0),   # m/s
    "T":   (-2.0, 35.0),   # °C
    "S":   ( 0.0, 42.0),   # PSU
    "Eta": (-3.0,  3.0),   # m
}

UNITS = {"U": "m/s", "V": "m/s", "T": "°C", "S": "PSU", "Eta": "m"}

CMAPS = {
    "U": "RdBu_r", "V": "RdBu_r", "T": "plasma", "S": "viridis", "Eta": "RdBu_r"
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _var_stats(da):
    arr = da.values.astype(np.float64)
    n_bad = int(np.sum(~np.isfinite(arr)))
    valid = arr[np.isfinite(arr)]
    if valid.size == 0:
        return dict(min=np.nan, mean=np.nan, max=np.nan, n_bad=n_bad, n=arr.size)
    return dict(
        min=float(valid.min()),
        mean=float(valid.mean()),
        max=float(valid.max()),
        n_bad=n_bad,
        n=int(arr.size),
    )


# ---------------------------------------------------------------------------
# Diagnostic figures
# ---------------------------------------------------------------------------

def _make_sections(data, boundary, out_path):
    """Time-mean depth × position cross-sections for one boundary."""
    ncols = 3
    nrows = 2
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 5 * nrows), squeeze=False)
    ax_flat = axes.ravel()

    for idx, var in enumerate(VARS):
        ax = ax_flat[idx]
        key = (var, boundary)
        if key not in data:
            ax.text(0.5, 0.5, f"{var}\nnot found", ha="center", va="center",
                    transform=ax.transAxes, color="grey")
            ax.set_title(var)
            continue

        da = data[key]
        pos_dim = [d for d in da.dims if d not in ("time", "depth")][0]
        pos = da.coords[pos_dim].values
        xlabel = "Longitude" if pos_dim == "lon" else "Latitude"
        lo, hi = PHYSICAL_BOUNDS.get(var, (None, None))
        cmap = CMAPS.get(var, "viridis")

        if da.ndim == 3:   # time × depth × position
            mean = da.mean(dim="time").values.astype(np.float32)
            depth = da.coords["depth"].values
            pcm = ax.pcolormesh(pos, depth, mean, shading="auto",
                                vmin=lo, vmax=hi, cmap=cmap)
            plt.colorbar(pcm, ax=ax, pad=0.02, shrink=0.8,
                         label=UNITS.get(var, ""))
            ax.invert_yaxis()
            ax.set_ylabel("Depth (m)")
        else:              # time × position (Eta)
            mean = da.mean(dim="time").values.astype(np.float32)
            ax.plot(pos, mean, color="steelblue", lw=0.8)
            ax.set_ylabel(f"Eta [{UNITS.get(var, '')}]")
            if lo is not None:
                ax.axhline(lo, color="red", lw=0.8, ls="--", alpha=0.7)
                ax.axhline(hi, color="red", lw=0.8, ls="--", alpha=0.7)
            ax.grid(True, alpha=0.3)

        ax.set_xlabel(xlabel)
        ax.set_title(f"{var} [{UNITS.get(var, '')}]")

    for ax in ax_flat[len(VARS):]:
        ax.set_visible(False)

    fig.suptitle(f"{boundary.capitalize()} boundary — time-mean cross-sections", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _make_timeseries(data, out_path):
    """Boundary-mean time series for each variable (all boundaries overlaid)."""
    n = len(VARS)
    fig, axes = plt.subplots(n, 1, figsize=(14, 2.5 * n), squeeze=False)

    for idx, var in enumerate(VARS):
        ax = axes[idx][0]
        for bnd in BOUNDARIES:
            key = (var, bnd)
            if key not in data:
                continue
            da = data[key]
            spatial_dims = [d for d in da.dims if d != "time"]
            ts = da.mean(dim=spatial_dims).values.astype(np.float32)
            ax.plot(da.coords["time"].values, ts, lw=0.7, label=bnd)
        ax.set_ylabel(f"{var} [{UNITS.get(var, '')}]", fontsize=8)
        ax.legend(fontsize=7, loc="upper right")
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    axes[-1][0].set_xlabel("Time")
    fig.suptitle("Boundary-mean time series per variable", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _make_depth_profiles(data, out_path):
    """Time- and boundary-mean depth profiles for T, S, U, V."""
    depth_vars = [v for v in VARS if v != "Eta"]
    n = len(depth_vars)
    fig, axes = plt.subplots(1, n, figsize=(3.5 * n, 7), squeeze=False)

    for idx, var in enumerate(depth_vars):
        ax = axes[0][idx]
        for bnd in BOUNDARIES:
            key = (var, bnd)
            if key not in data or data[key].ndim != 3:
                continue
            da = data[key]
            pos_dims = [d for d in da.dims if d not in ("time", "depth")]
            profile = da.mean(dim=["time"] + pos_dims).values.astype(np.float32)
            depth = da.coords["depth"].values
            ax.plot(profile, depth, lw=0.9, label=bnd)
        ax.invert_yaxis()
        ax.set_xlabel(f"{var} [{UNITS.get(var, '')}]", fontsize=9)
        if idx == 0:
            ax.set_ylabel("Depth (m)")
        ax.legend(fontsize=7)
        ax.grid(True, alpha=0.3)
        if var in PHYSICAL_BOUNDS:
            lo, hi = PHYSICAL_BOUNDS[var]
            ax.axvline(lo, color="red", lw=0.8, ls="--", alpha=0.7)
            ax.axvline(hi, color="red", lw=0.8, ls="--", alpha=0.7)

    fig.suptitle("Time- and boundary-mean depth profiles  (red dashes = expected bounds)",
                 fontsize=11)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = common.cli()

    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)

    simulation_directory = config["simulation_directory"]
    working_directory    = config["working_directory"]
    simulation_input_dir = os.path.join(simulation_directory, "input")

    review_dir = os.path.join(simulation_directory, "review", "ocean_bcs")
    os.makedirs(review_dir, exist_ok=True)

    print("Loading OBC binary files...")
    data = common.load_obc_binaries(simulation_input_dir, working_directory, config)

    # ------------------------------------------------------------------
    # Diagnostic figures
    # ------------------------------------------------------------------
    print("Generating diagnostic figures...")
    for bnd in BOUNDARIES:
        _make_sections(data, bnd, os.path.join(review_dir, f"sections_{bnd}.png"))
    _make_timeseries(data, os.path.join(review_dir, "timeseries.png"))
    _make_depth_profiles(data, os.path.join(review_dir, "depth_profiles.png"))

    # ------------------------------------------------------------------
    # Per-(variable, boundary) statistics and checks
    # ------------------------------------------------------------------
    print("Computing statistics and running QC checks...")

    all_pass = True
    stat_rows = []
    detail_lines = []
    bin_rows = []

    for var in VARS:
        for bnd in BOUNDARIES:
            key = (var, bnd)
            if key not in data:
                stat_rows.append((var, bnd, "—", "—", "—", "—", "—"))
                continue

            da = data[key]
            st = _var_stats(da)
            checks = []

            # NaN / Inf
            if st["n_bad"] == 0:
                checks.append((True, "No NaN/Inf values"))
            else:
                pct = 100.0 * st["n_bad"] / st["n"]
                checks.append((False, f"{st['n_bad']:,} NaN/Inf ({pct:.2f} %)"))
                all_pass = False

            # Physical range
            if var in PHYSICAL_BOUNDS:
                lo, hi = PHYSICAL_BOUNDS[var]
                in_range = st["min"] >= lo and st["max"] <= hi
                if in_range:
                    checks.append((True, f"Within expected range [{lo:g}, {hi:g}]"))
                else:
                    checks.append((
                        False,
                        f"Outside expected range [{lo:g}, {hi:g}]: "
                        f"actual [{st['min']:.4g}, {st['max']:.4g}]",
                    ))
                    all_pass = False

            overall_ok = all(ok for ok, _ in checks)
            nan_icon   = "✓" if checks[0][0] else "✗"
            range_icon = ("✓" if checks[1][0] else "✗") if len(checks) > 1 else "—"

            stat_rows.append((
                var, bnd,
                f"{st['min']:.4g}", f"{st['mean']:.4g}", f"{st['max']:.4g}",
                f"{nan_icon} {st['n_bad']:,}", range_icon,
            ))

            if not overall_ok:
                detail_lines.append(f"### `{var}.{bnd}`")
                for ok, msg in checks:
                    detail_lines.append(f"- {'✓' if ok else '✗'} {msg}")
                detail_lines.append("")

            # Binary size check
            bin_path = os.path.join(simulation_input_dir, f"{var}.{bnd}.bin")
            expected = int(np.prod(da.shape)) * 4
            actual   = os.path.getsize(bin_path) if os.path.exists(bin_path) else 0
            size_ok  = actual == expected
            if not size_ok:
                all_pass = False
            bin_rows.append((
                f"`{var}.{bnd}.bin`", "✓",
                "✓" if size_ok else "✗",
                f"{actual:,}", f"{expected:,}",
            ))

    # ------------------------------------------------------------------
    # Assemble Markdown report
    # ------------------------------------------------------------------
    status = "PASS" if all_pass else "FAIL"
    now    = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Ocean Boundary Conditions QC Report",
        "",
        f"**Overall status: {status}**  ",
        f"**Config:** `{args.config_file}`  ",
        f"**Generated:** {now}",
        "",
        "## Per-Variable Statistics",
        "",
        "| Variable | Boundary | Min | Mean | Max | NaN/Inf | Range |",
        "|----------|----------|-----|------|-----|---------|-------|",
    ]
    for row in stat_rows:
        lines.append(
            f"| `{row[0]}` | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} | {row[6]} |"
        )

    lines += [
        "",
        "## Binary File Verification",
        "",
        "| File | Exists | Size OK | Actual bytes | Expected bytes |",
        "|------|--------|---------|--------------|----------------|",
    ]
    for row in bin_rows:
        lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |")

    if detail_lines:
        lines += ["", "## Failing Check Details", ""] + detail_lines

    lines += [
        "",
        "## Diagnostic Figures",
        "",
        "| Figure | Description |",
        "|--------|-------------|",
        "| `sections_south.png` | Time-mean cross-sections at south boundary |",
        "| `sections_north.png` | Time-mean cross-sections at north boundary |",
        "| `sections_west.png`  | Time-mean cross-sections at west boundary  |",
        "| `sections_east.png`  | Time-mean cross-sections at east boundary  |",
        "| `timeseries.png`     | Boundary-mean time series per variable     |",
        "| `depth_profiles.png` | Time- and boundary-mean depth profiles     |",
    ]

    report_path = os.path.join(review_dir, "report.md")
    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nReport written to {report_path}")
    print(f"Overall QC status: {status}")
    if not all_pass:
        sys.exit(1)


if __name__ == "__main__":
    main()
