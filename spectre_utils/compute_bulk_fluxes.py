"""
compute_bulk_fluxes.py
======================
Compute MITgcm EXF bulk formula fluxes from the first atmospheric forcing
record and the initial ocean SST, and report whether any computed values
exceed the EXF default range-check thresholds.

Grid handling
-------------
Atmospheric forcing is on the ERA5 regular grid (161 × 321, 0.25 deg,
20–60 N, -90 to -10 E).  The ocean initial temperature (T.init.bin) is on
the curvilinear model grid (424 × 768 × 50).  Because the curvilinear grid
coordinates are not directly embedded in the input binary files, the two
grids are NOT spatially matched here.  Instead the script uses the SST
statistics (min, mean, max, percentiles) from T.init.bin — restricted to
ocean cells using derived_bathy.bin — as a representative range, then
evaluates the bulk formula across all ERA5 forcing-grid points for each
representative SST value.  This bounds the possible hflux values given the
real atmospheric inputs and the real ocean state distribution.

Bulk formula (simplified MITgcm EXF, constant transfer coefficients)
----------------------------------------------------------------------
  tau   = rho_a * Cd * |U| * (u, v)           wind stress [N/m²]
  q_sat = saltsat * 0.622 * e_s / (p - 0.378 * e_s)   sat. spec. hum.
          where e_s = cvapor_fac * exp(-cvapor_exp / T_skin_K)
  QL    = rho_a * L_v * Ce * |U| * (q_sat - q_air)     latent heat [W/m²]
  QH    = rho_a * Cp * Ch * |U| * (T_skin_K - T_air_K) sensible heat [W/m²]
  Q_SW  = swdown * (1 - albedo)                          net SW [W/m²]
  Q_LW  = lwdown - eps * sigma * T_skin_K**4            net LW [W/m²]
  hflux = Q_SW + Q_LW - QL - QH                         (positive = into ocean)

Constants match those echoed in MITgcm STDOUT (exf_set_defaults).

Usage
-----
    uv run python spectre_utils/compute_bulk_fluxes.py <input_dir> [<record_index>]

    input_dir     : path to the simulation input/ directory
    record_index  : 0-based index of the forcing record to use (default 0)
"""

import sys
import numpy as np

# ---------------------------------------------------------------------------
# MITgcm EXF constants (from STDOUT echo of exf_set_defaults)
# ---------------------------------------------------------------------------
RHO_A       = 1.200        # kg/m³  atmrho
CP_A        = 1005.0       # J/(kg·K)  atmcp
L_V         = 2.500e6      # J/kg  flamb
CVAPOR_FAC  = 640380.0     # cvapor_fac
CVAPOR_EXP  = 5107.4       # cvapor_exp
SALTSAT     = 0.980        # reduction of Qsat over salty water
ALBEDO      = 0.100        # exf_albedo
EPSILON     = 0.970        # LW emissivity (standard value)
SIGMA       = 5.6704e-8    # Stefan-Boltzmann [W/m²/K⁴]
CD          = 1.3e-3       # drag coefficient (momentum)
CE          = 1.4e-3       # Dalton number (latent heat)
CH          = 1.4e-3       # Stanton number (sensible heat)
CEN2KEL     = 273.15       # °C to K

# EXF default range-check thresholds
EXF_HFLUX_MIN  = -2000.0   # W/m²
EXF_HFLUX_MAX  =  2000.0
EXF_VSTR_MIN   =    -2.0   # N/m²
EXF_VSTR_MAX   =     2.0

# Forcing / ocean grid dimensions
NX_ERA   = 321
NY_ERA   = 161
NX_MODEL = 768
NY_MODEL = 424
NZ_MODEL = 50


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def read_record(path: str, ny: int, nx: int, rec: int) -> np.ndarray:
    """Read a single 2-D record (big-endian float32) from a binary file."""
    offset = rec * ny * nx
    arr = np.fromfile(path, dtype=">f4", count=ny * nx, offset=offset * 4)
    if arr.size < ny * nx:
        raise IOError(f"{path}: expected {ny*nx} values at record {rec}, got {arr.size}")
    return arr.reshape(ny, nx).astype(np.float64)


def saturation_specific_humidity(T_K: np.ndarray, p_atm: float = 101325.0) -> np.ndarray:
    """MITgcm EXF saturation specific humidity formula."""
    e_s = CVAPOR_FAC * np.exp(-CVAPOR_EXP / np.maximum(T_K, 100.0))
    return SALTSAT * 0.622 * e_s / (p_atm - 0.378 * e_s)


def bulk_fluxes(
    sst_c: float,
    atemp_K: np.ndarray,
    aqh: np.ndarray,
    uwind: np.ndarray,
    vwind: np.ndarray,
    swdown: np.ndarray,
    lwdown: np.ndarray,
) -> dict:
    """Compute bulk fluxes on the atmospheric forcing grid for a given SST."""
    T_skin_K = sst_c + CEN2KEL

    wind_speed = np.sqrt(uwind**2 + vwind**2)

    # Saturation specific humidity at SST
    q_sat = saturation_specific_humidity(T_skin_K)

    # Latent heat flux (positive = into ocean = condensation)
    QL = RHO_A * L_V * CE * wind_speed * (q_sat - aqh)

    # Sensible heat flux (positive = into ocean = warm air over cold ocean)
    QH = RHO_A * CP_A * CH * wind_speed * (T_skin_K - atemp_K)

    # Net shortwave (into ocean)
    Q_SW = swdown * (1.0 - ALBEDO)

    # Net longwave (into ocean; negative when ocean emits more than it receives)
    Q_LW = lwdown - EPSILON * SIGMA * T_skin_K**4

    hflux = Q_SW + Q_LW - QL - QH

    # Wind stress components
    ustress = RHO_A * CD * wind_speed * uwind
    vstress = RHO_A * CD * wind_speed * vwind

    return dict(
        hflux=hflux, ustress=ustress, vstress=vstress,
        QL=QL, QH=QH, Q_SW=Q_SW, Q_LW=Q_LW,
        wind_speed=wind_speed,
    )


def stats(arr: np.ndarray, label: str) -> None:
    print(f"    {label:14s}  min={arr.min():10.4g}  mean={arr.mean():10.4g}  max={arr.max():10.4g}")


def check_threshold(arr: np.ndarray, lo: float, hi: float, name: str) -> bool:
    n_low  = int((arr < lo).sum())
    n_high = int((arr > hi).sum())
    n_tot  = arr.size
    ok = (n_low == 0) and (n_high == 0)
    flag = "OK" if ok else "*** EXCEEDS THRESHOLD ***"
    print(f"    {name:10s}  threshold [{lo:g}, {hi:g}]  "
          f"n_below={n_low:6d}  n_above={n_high:6d}  "
          f"(of {n_tot:6d} pts)  {flag}")
    return ok


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    input_dir = sys.argv[1].rstrip("/")
    rec = int(sys.argv[2]) if len(sys.argv) > 2 else 0

    print(f"\n{'='*70}")
    print(f" MITgcm EXF bulk flux diagnostic")
    print(f" Input dir : {input_dir}")
    print(f" Record    : {rec}  (0-based, 3-hourly ERA5)")
    print(f"{'='*70}\n")

    # ------------------------------------------------------------------
    # 1. Read first atmospheric forcing record
    # ------------------------------------------------------------------
    print("Loading atmospheric forcing ...")
    atm = {}
    for name in ("atemp", "aqh", "uwind", "vwind", "swdown", "lwdown"):
        try:
            atm[name] = read_record(f"{input_dir}/{name}.bin", NY_ERA, NX_ERA, rec)
            stats(atm[name], name)
        except Exception as e:
            print(f"  ERROR reading {name}: {e}")
            sys.exit(1)
    print()

    # ------------------------------------------------------------------
    # 2. Read initial ocean SST, masking land with derived_bathy.bin
    # ------------------------------------------------------------------
    print("Loading initial ocean SST from T.init.bin (top level) ...")
    t_path    = f"{input_dir}/T.init.bin"
    bath_path = f"{input_dir}/derived_bathy.bin"

    try:
        sst_flat = np.fromfile(t_path, dtype=">f4",
                               count=NY_MODEL * NX_MODEL).astype(np.float64)
        sst_2d = sst_flat.reshape(NY_MODEL, NX_MODEL)
    except Exception as e:
        print(f"  ERROR reading T.init.bin: {e}")
        sys.exit(1)

    # Ocean mask: bathy != 0  (0 = land in MITgcm convention)
    try:
        bathy = np.fromfile(bath_path, dtype=">f4",
                            count=NY_MODEL * NX_MODEL).reshape(NY_MODEL, NX_MODEL)
        ocean_mask = bathy != 0.0
        print(f"  Ocean points: {ocean_mask.sum()} / {ocean_mask.size} "
              f"({100*ocean_mask.mean():.1f} %)")
    except Exception as e:
        print(f"  WARNING: could not read bathymetry ({e}); using all points")
        ocean_mask = np.ones((NY_MODEL, NX_MODEL), dtype=bool)

    sst_ocean = sst_2d[ocean_mask]
    print(f"  SST (ocean pts, n={sst_ocean.size}):")
    for pct, label in [(5,"p05"), (25,"p25"), (50,"p50"), (75,"p75"), (95,"p95")]:
        print(f"    {label}: {np.percentile(sst_ocean, pct):.2f} °C")
    print(f"    min:  {sst_ocean.min():.2f} °C")
    print(f"    mean: {sst_ocean.mean():.2f} °C")
    print(f"    max:  {sst_ocean.max():.2f} °C")
    print()

    # ------------------------------------------------------------------
    # 3. Evaluate bulk fluxes for representative SST values
    # ------------------------------------------------------------------
    sst_cases = {
        "SST_min":  float(sst_ocean.min()),
        "SST_p05":  float(np.percentile(sst_ocean, 5)),
        "SST_p25":  float(np.percentile(sst_ocean, 25)),
        "SST_mean": float(sst_ocean.mean()),
        "SST_p75":  float(np.percentile(sst_ocean, 75)),
        "SST_max":  float(sst_ocean.max()),
    }

    all_pass = True
    for case_name, sst_c in sst_cases.items():
        print(f"--- {case_name} = {sst_c:.2f} °C ---")
        fl = bulk_fluxes(
            sst_c,
            atm["atemp"], atm["aqh"],
            atm["uwind"], atm["vwind"],
            atm["swdown"], atm["lwdown"],
        )

        stats(fl["Q_SW"],      "net SW")
        stats(fl["Q_LW"],      "net LW")
        stats(fl["QL"],        "latent (QL)")
        stats(fl["QH"],        "sensible (QH)")
        stats(fl["hflux"],     "hflux")
        stats(fl["vstress"],   "vstress")
        stats(fl["wind_speed"],"wind speed")
        print()

        ok_h  = check_threshold(fl["hflux"],  EXF_HFLUX_MIN, EXF_HFLUX_MAX, "hflux")
        ok_vs = check_threshold(fl["vstress"], EXF_VSTR_MIN,  EXF_VSTR_MAX,  "vstress")
        ok_us = check_threshold(fl["ustress"], EXF_VSTR_MIN,  EXF_VSTR_MAX,  "ustress")
        if not (ok_h and ok_vs and ok_us):
            all_pass = False
        print()

    # ------------------------------------------------------------------
    # 4. Worst-case grid point (using mean SST)
    # ------------------------------------------------------------------
    print("--- Worst-case grid point (ERA5 grid, SST = ocean mean) ---")
    fl_mean = bulk_fluxes(
        sst_cases["SST_mean"],
        atm["atemp"], atm["aqh"],
        atm["uwind"], atm["vwind"],
        atm["swdown"], atm["lwdown"],
    )
    idx = np.unravel_index(np.abs(fl_mean["hflux"]).argmax(), fl_mean["hflux"].shape)
    j, i = idx
    lat = 20.0 + j * 0.25
    lon = -90.0 + i * 0.25
    print(f"  Location : j={j}, i={i}  ({lat:.2f} N, {lon:.2f} E)")
    print(f"  atemp    = {atm['atemp'][j,i]:.2f} K  ({atm['atemp'][j,i]-273.15:.2f} °C)")
    print(f"  aqh      = {atm['aqh'][j,i]:.5f} kg/kg")
    print(f"  uwind    = {atm['uwind'][j,i]:.2f} m/s")
    print(f"  vwind    = {atm['vwind'][j,i]:.2f} m/s")
    print(f"  swdown   = {atm['swdown'][j,i]:.2f} W/m²")
    print(f"  lwdown   = {atm['lwdown'][j,i]:.2f} W/m²")
    hf = fl_mean['hflux'][j, i]
    print(f"  hflux    = {hf:.2f} W/m²  (SST = {sst_cases['SST_mean']:.2f} °C)")

    print(f"\n{'='*70}")
    print(f" Overall: {'PASS' if all_pass else 'FAIL — some values exceed EXF thresholds'}")
    print(f"{'='*70}\n")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
