"""
QC review of EXF atmospheric forcing fields.

Loads the written binary forcing files, runs physical range / consistency /
temporal checks, verifies binary file sizes, and writes a Markdown report
plus three diagnostic figures to:

    <simulation_directory>/review/atmosphere/
        report.md
        mean_maps.png      -- temporal-mean spatial map per variable
        timeseries.png     -- domain-mean time series per variable
        histograms.png     -- value distributions per variable
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

# ---------------------------------------------------------------------------
# Physical plausibility bounds (min, max) keyed by mitgcm_name.
# Values outside these ranges raise a warning in the report.
# ---------------------------------------------------------------------------
PHYSICAL_BOUNDS: dict[str, tuple[float, float]] = {
    "uwind":    (-70.0,   70.0),    # m/s
    "vwind":    (-70.0,   70.0),    # m/s
    "atemp":    (200.0,  340.0),    # K
    "d2m":      (200.0,  340.0),    # K  (dewpoint, same scale as atemp)
    "aqh":      (  0.0,   0.05),    # kg/kg
    "swdown":   (  0.0, 1400.0),    # W/m²  (after scale_factor)
    "lwdown":   (  0.0,  700.0),    # W/m²  (after scale_factor)
    "precip":   (-1e-5,   0.05),    # m  (tiny ERA5 negatives are common)
    "evap":     ( -0.05,  0.05),    # m
    "runoff":   (  0.0,   1.0),     # m
    "pressure": (80000., 115000.),  # Pa
    "sp":       (80000., 115000.),  # Pa
}

# Variables that should be non-negative after any scale factor
NON_NEGATIVE = {"swdown", "lwdown", "precip", "runoff", "aqh"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _var_stats(da: xr.DataArray) -> dict:
    """Compute global min/mean/max and count of non-finite values (lazy-safe)."""
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


def _check_binary(path: str, nt: int, ny: int, nx: int) -> tuple[bool, bool, int, int]:
    """Return (exists, size_ok, actual_bytes, expected_bytes)."""
    expected = nt * ny * nx * 4
    if not os.path.exists(path):
        return False, False, 0, expected
    actual = os.path.getsize(path)
    return True, actual == expected, actual, expected


def _check_temporal_spacing(ds: xr.Dataset) -> tuple[bool, str]:
    """Verify that valid_time steps are uniformly spaced."""
    times = ds["valid_time"].values
    if len(times) < 2:
        return True, "Only one time step — cannot check spacing."
    diffs = np.diff(times.astype("datetime64[s]").astype(np.int64))
    unique_diffs = np.unique(diffs)
    if len(unique_diffs) == 1:
        dt_h = unique_diffs[0] / 3600
        return True, f"Uniform spacing of {dt_h:.0f} h across {len(times)} steps."
    dt_h = diffs / 3600
    return (
        False,
        f"Non-uniform time spacing: min={dt_h.min():.1f} h, max={dt_h.max():.1f} h "
        f"({len(unique_diffs)} distinct intervals).",
    )


# ---------------------------------------------------------------------------
# Diagnostic figures
# ---------------------------------------------------------------------------

def _make_mean_maps(ds: xr.Dataset, var_names: list[str], out_path: str) -> None:
    present = [n for n in var_names if n in ds]
    n = len(present)
    if n == 0:
        return
    ncols = min(3, n)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(6 * ncols, 4 * nrows), squeeze=False)

    for idx, name in enumerate(present):
        ax = axes[idx // ncols][idx % ncols]
        da_mean = ds[name].mean(dim="valid_time").compute()
        lat = da_mean.coords.get("latitude")
        lon = da_mean.coords.get("longitude")
        if lat is not None and lon is not None:
            pcm = ax.pcolormesh(lon.values, lat.values, da_mean.values,
                                shading="auto", cmap="RdBu_r")
            plt.colorbar(pcm, ax=ax, pad=0.02, shrink=0.8)
            ax.set_xlabel("Lon")
            ax.set_ylabel("Lat")
        else:
            ax.plot(da_mean.values.ravel()[:2000])
        var_units = ds[name].attrs.get("units", "")
        ax.set_title(f"{name} [{var_units}]" if var_units else name)

    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle("Temporal mean", fontsize=13)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _make_timeseries(ds: xr.Dataset, var_names: list[str], out_path: str) -> None:
    present = [n for n in var_names if n in ds]
    n = len(present)
    if n == 0:
        return
    fig, axes = plt.subplots(n, 1, figsize=(14, 2.2 * n), squeeze=False)

    for idx, name in enumerate(present):
        ax = axes[idx][0]
        spatial_dims = [d for d in ds[name].dims if d != "valid_time"]
        ts = ds[name].mean(dim=spatial_dims).compute()
        ax.plot(ts["valid_time"].values, ts.values, lw=0.7, color="steelblue")
        ax.set_ylabel(name, fontsize=8)
        ax.grid(True, alpha=0.3)
        ax.tick_params(labelsize=7)

    axes[-1][0].set_xlabel("Time")
    fig.suptitle("Domain-mean time series", fontsize=12)
    fig.tight_layout()
    fig.savefig(out_path, dpi=120, bbox_inches="tight")
    plt.close(fig)


def _make_histograms(ds: xr.Dataset, var_names: list[str], out_path: str) -> None:
    present = [n for n in var_names if n in ds]
    n = len(present)
    if n == 0:
        return
    ncols = min(3, n)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(nrows, ncols, figsize=(5 * ncols, 3 * nrows), squeeze=False)

    for idx, name in enumerate(present):
        ax = axes[idx // ncols][idx % ncols]
        vals = ds[name].values.ravel()
        vals = vals[np.isfinite(vals)]
        ax.hist(vals, bins=120, color="steelblue", edgecolor="none", density=True)
        var_units = ds[name].attrs.get("units", "")
        ax.set_xlabel(f"{name} [{var_units}]" if var_units else name, fontsize=8)
        ax.set_ylabel("Density", fontsize=8)
        ax.tick_params(labelsize=7)
        if name in PHYSICAL_BOUNDS:
            lo, hi = PHYSICAL_BOUNDS[name]
            for bound in (lo, hi):
                ax.axvline(bound, color="red", lw=0.8, linestyle="--", alpha=0.7)

    for idx in range(n, nrows * ncols):
        axes[idx // ncols][idx % ncols].set_visible(False)

    fig.suptitle("Value distributions  (red dashes = expected bounds)", fontsize=11)
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

    working_directory = config["working_directory"]
    simulation_directory = config["simulation_directory"]
    years = config["atmosphere"]["years"]
    atm_vars = config["atmosphere"]["variables"]
    computed_vars = config["atmosphere"].get("computed_variables", [])
    prefix = config["atmosphere"]["prefix"]
    simulation_input_dir = os.path.join(simulation_directory, "input")

    t1 = datetime.strptime(config["domain"]["time"]["start"], "%Y-%m-%d")
    t2 = datetime.strptime(config["domain"]["time"]["end"], "%Y-%m-%d")

    review_dir = os.path.join(simulation_directory, "review", "atmosphere")
    os.makedirs(review_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Build ordered list of all mitgcm names (configured + computed)
    # ------------------------------------------------------------------
    seen: set[str] = set()
    all_names: list[str] = []
    for var in atm_vars:
        n = var["mitgcm_name"]
        if n not in seen:
            seen.add(n)
            all_names.append(n)
    for cv in computed_vars:
        n = cv["mitgcm_name"]
        if n not in seen:
            seen.add(n)
            all_names.append(n)

    # ------------------------------------------------------------------
    # Load binary forcing files
    # ------------------------------------------------------------------
    print("Loading EXF binary files...")
    ds = common.load_exf_binaries(
        simulation_input_dir, all_names, working_directory, prefix, years, atm_vars, t1, t2
    )

    nt = ds.sizes["valid_time"]
    ny = ds.sizes.get("latitude")
    nx = ds.sizes.get("longitude")

    # ------------------------------------------------------------------
    # Diagnostic figures
    # ------------------------------------------------------------------
    print("Generating diagnostic figures...")
    _make_mean_maps(ds, all_names, os.path.join(review_dir, "mean_maps.png"))
    _make_timeseries(ds, all_names, os.path.join(review_dir, "timeseries.png"))
    _make_histograms(ds, all_names, os.path.join(review_dir, "histograms.png"))

    # ------------------------------------------------------------------
    # Per-variable statistics and checks
    # ------------------------------------------------------------------
    print("Computing statistics and running QC checks...")

    all_pass = True

    # Table rows: (name, min, mean, max, n_bad, range_icon)
    stat_rows: list[tuple] = []
    # Per-variable check details for the detailed section
    detail_lines: list[str] = []

    for name in all_names:
        if name not in ds:
            stat_rows.append((name, "—", "—", "—", "—", "—"))
            continue

        st = _var_stats(ds[name])
        checks: list[tuple[bool, str]] = []

        # 1. NaN / Inf
        if st["n_bad"] == 0:
            checks.append((True, "No NaN/Inf values"))
        else:
            pct = 100.0 * st["n_bad"] / st["n"]
            checks.append((False, f"{st['n_bad']:,} NaN/Inf values ({pct:.2f} %)"))
            all_pass = False

        # 2. Physical range
        if name in PHYSICAL_BOUNDS:
            lo, hi = PHYSICAL_BOUNDS[name]
            if st["min"] >= lo and st["max"] <= hi:
                checks.append((True, f"Within expected range [{lo:g}, {hi:g}]"))
            else:
                checks.append((
                    False,
                    f"Outside expected range [{lo:g}, {hi:g}]: "
                    f"actual [{st['min']:.4g}, {st['max']:.4g}]",
                ))
                all_pass = False

        # 3. Non-negative where required
        if name in NON_NEGATIVE:
            n_neg = int((ds[name] < 0).sum().compute().item())
            if n_neg == 0:
                checks.append((True, "All values ≥ 0"))
            else:
                pct = 100.0 * n_neg / st["n"]
                checks.append((False, f"{n_neg:,} negative values ({pct:.3f} %)"))
                all_pass = False

        overall_ok = all(ok for ok, _ in checks)
        range_ok = checks[1][0] if len(checks) > 1 else None
        range_icon = ("✓" if range_ok else "✗") if range_ok is not None else "—"
        nan_icon = "✓" if checks[0][0] else "✗"

        stat_rows.append((
            name,
            f"{st['min']:.4g}",
            f"{st['mean']:.4g}",
            f"{st['max']:.4g}",
            f"{nan_icon} {st['n_bad']:,}",
            range_icon,
        ))

        if not overall_ok:
            detail_lines.append(f"### `{name}`")
            for ok, msg in checks:
                detail_lines.append(f"- {'✓' if ok else '✗'} {msg}")
            detail_lines.append("")

    # ------------------------------------------------------------------
    # Cross-variable consistency checks
    # ------------------------------------------------------------------
    consistency: list[tuple[str, bool, str]] = []

    # Temporal spacing
    ok, msg = _check_temporal_spacing(ds)
    if not ok:
        all_pass = False
    consistency.append(("Uniform time spacing", ok, msg))

    # Dewpoint ≤ air temperature
    if "d2m" in ds and "atemp" in ds:
        n_viol = int((ds["d2m"] > ds["atemp"]).sum().compute().item())
        n_total = int(ds["d2m"].size)
        ok = n_viol == 0
        msg = (
            "Dewpoint ≤ air temperature everywhere"
            if ok
            else f"Dewpoint > air temperature in {n_viol:,}/{n_total:,} cells "
                 f"({100.0*n_viol/n_total:.2f} %)"
        )
        if not ok:
            all_pass = False
        consistency.append(("Dewpoint ≤ air temperature", ok, msg))

    # Seasonal cycle in swdown (sanity check: CV should be meaningful)
    if "swdown" in ds:
        sw = ds["swdown"]
        spatial_dims = [d for d in sw.dims if d != "valid_time"]
        domain_mean_ts = sw.mean(dim=spatial_dims).compute().values
        domain_mean_ts = domain_mean_ts[np.isfinite(domain_mean_ts)]
        if domain_mean_ts.size > 1:
            cv = domain_mean_ts.std() / (domain_mean_ts.mean() + 1e-30)
            ok = cv > 0.2
            msg = f"Temporal CV = {cv:.3f} ({'seasonal signal present' if ok else 'weak seasonal signal — check data'})"
            if not ok:
                all_pass = False
            consistency.append(("swdown seasonal cycle", ok, msg))

    # ------------------------------------------------------------------
    # Binary file verification
    # ------------------------------------------------------------------
    bin_rows: list[tuple] = []
    if ny is not None and nx is not None:
        written: set[str] = set()
        for var in atm_vars:
            n = var["mitgcm_name"]
            if n in written:
                continue
            written.add(n)
            path = os.path.join(simulation_input_dir, f"{n}.bin")
            exists, size_ok, actual, expected = _check_binary(path, nt, ny, nx)
            if not exists or not size_ok:
                all_pass = False
            bin_rows.append((
                f"`{n}.bin`",
                "✓" if exists else "✗",
                ("✓" if size_ok else "✗") if exists else "—",
                f"{actual:,}",
                f"{expected:,}",
            ))
        for cv in computed_vars:
            n = cv["mitgcm_name"]
            path = os.path.join(simulation_input_dir, f"{n}.bin")
            exists, size_ok, actual, expected = _check_binary(path, nt, ny, nx)
            if not exists or not size_ok:
                all_pass = False
            bin_rows.append((
                f"`{n}.bin`",
                "✓" if exists else "✗",
                ("✓" if size_ok else "✗") if exists else "—",
                f"{actual:,}",
                f"{expected:,}",
            ))

    # ------------------------------------------------------------------
    # Assemble Markdown report
    # ------------------------------------------------------------------
    status = "PASS" if all_pass else "FAIL"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines: list[str] = [
        f"# Atmospheric Forcing QC Report",
        f"",
        f"**Overall status: {status}**  ",
        f"**Config:** `{args.config_file}`  ",
        f"**Time range:** {t1.date()} – {t2.date()}  ",
        f"**Grid:** {nt} time steps × {ny} lat × {nx} lon  ",
        f"**Generated:** {now}",
        f"",
        f"## Per-Variable Statistics",
        f"",
        f"| Variable | Min | Mean | Max | NaN/Inf | Range |",
        f"|----------|-----|------|-----|---------|-------|",
    ]
    for row in stat_rows:
        lines.append(f"| `{row[0]}` | {row[1]} | {row[2]} | {row[3]} | {row[4]} | {row[5]} |")

    lines += [
        f"",
        f"## Consistency Checks",
        f"",
    ]
    for label, ok, msg in consistency:
        lines.append(f"- {'✓' if ok else '✗'} **{label}:** {msg}")

    if bin_rows:
        lines += [
            f"",
            f"## Binary File Verification",
            f"",
            f"Expected size = nt × ny × nx × 4 bytes = {nt} × {ny} × {nx} × 4 = {nt*ny*nx*4:,} bytes",
            f"",
            f"| File | Exists | Size OK | Actual bytes | Expected bytes |",
            f"|------|--------|---------|--------------|----------------|",
        ]
        for row in bin_rows:
            lines.append(f"| {row[0]} | {row[1]} | {row[2]} | {row[3]} | {row[4]} |")
    else:
        lines += [
            f"",
            f"*Binary verification skipped — could not determine grid dimensions.*",
        ]

    if detail_lines:
        lines += [
            f"",
            f"## Failing Check Details",
            f"",
        ] + detail_lines

    lines += [
        f"",
        f"## Diagnostic Figures",
        f"",
        f"| Figure | Description |",
        f"|--------|-------------|",
        f"| `mean_maps.png` | Temporal-mean spatial map for each variable |",
        f"| `timeseries.png` | Domain-mean time series for each variable |",
        f"| `histograms.png` | Value distributions (red dashes = expected bounds) |",
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
