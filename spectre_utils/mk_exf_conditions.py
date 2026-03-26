"""
mk_exf_conditions.py
====================
Convert ERA5 NetCDF atmospheric forcing into big-endian float32 binary files
on the **model curvilinear grid**.

All fields are bilinearly interpolated from the ERA5 0.25° regular grid to
model cell-centre positions.  Wind components (uwind, vwind) are additionally
rotated from geographic (east, north) to model-grid (i, j) directions.

Because the output is already on the model grid, EXF interpolation must be
disabled in data.exf (remove *_nlon / *_nlat / *_lon0 / *_lat0 / *_lon_inc /
*_lat_inc entries from EXF_NML_04 for every field) and
rotateStressOnAgrid = .FALSE.
"""

import os
import sys
from spectre_utils import common
import yaml
from metpy.calc import specific_humidity_from_dewpoint
from metpy.units import units
from datetime import datetime
import numpy as np
import xarray as xr
from scipy.interpolate import RegularGridInterpolator

TIME_CHUNK = 744

# Wind variable names that form a vector pair requiring rotation.
WIND_VARS = {"uwind", "vwind"}


# ---------------------------------------------------------------------------
# Model grid helpers
# ---------------------------------------------------------------------------

def read_model_grid(horizgridfile, Nx, Ny):
    """Read cell-centre lon/lat from the MITgcm curvilinear horizgridfile."""
    arr = np.fromfile(horizgridfile, dtype=">f8")
    fields = arr.reshape(16, Ny + 1, Nx + 1)
    xC = fields[0, :Ny, :Nx]
    yC = fields[1, :Ny, :Nx]
    return xC, yC


def compute_rotation_angles(xC, yC):
    """Return (angleCS, angleSN) from the i-direction of the curvilinear grid."""
    dlon = np.empty_like(xC)
    dlat = np.empty_like(yC)
    dlon[:, 1:-1] = xC[:, 2:] - xC[:, :-2]
    dlat[:, 1:-1] = yC[:, 2:] - yC[:, :-2]
    dlon[:, 0] = xC[:, 1] - xC[:, 0]
    dlat[:, 0] = yC[:, 1] - yC[:, 0]
    dlon[:, -1] = xC[:, -1] - xC[:, -2]
    dlat[:, -1] = yC[:, -1] - yC[:, -2]
    angle = np.arctan2(dlat, dlon * np.cos(np.deg2rad(yC)))
    return np.cos(angle), np.sin(angle)


# ---------------------------------------------------------------------------
# ERA5 I/O
# ---------------------------------------------------------------------------

def _open_var(working_directory, prefix, mitgcm_name, years, t1, t2):
    """Open a single ERA5 variable across all years as a lazily-chunked dataset."""
    files = [f"{working_directory}/{prefix}_{mitgcm_name}_{year}.nc" for year in years]
    for fp in files:
        if not os.path.exists(fp):
            print(f"Missing file: {fp}", file=sys.stderr)
            sys.exit(1)
    ds = xr.open_mfdataset(files, combine="by_coords", chunks={"valid_time": TIME_CHUNK}).sel(
        valid_time=slice(t1, t2)
    )
    data_vars = list(ds.data_vars)
    if len(data_vars) == 1 and data_vars[0] != mitgcm_name:
        ds = ds.rename({data_vars[0]: mitgcm_name})
    # ERA5 latitude is stored north-to-south (60→20 N). Flip to south-to-north.
    ds = ds.isel(latitude=slice(None, None, -1))
    return ds


# ---------------------------------------------------------------------------
# Interpolation
# ---------------------------------------------------------------------------

def interp_scalar_chunk(era5_lat, era5_lon, data_2d, pts, Ny, Nx):
    """Bilinear interpolation of a single 2-D ERA5 field to model grid points."""
    interp = RegularGridInterpolator(
        (era5_lat, era5_lon), data_2d, method="linear",
        bounds_error=False, fill_value=None,
    )
    return interp(pts).reshape(Ny, Nx).astype(np.float32)


def interp_and_rotate_wind_chunk(era5_lat, era5_lon, u_2d, v_2d,
                                  pts, Ny, Nx, angleCS, angleSN):
    """Interpolate u/v and rotate from geographic to model-grid axes."""
    iu = RegularGridInterpolator(
        (era5_lat, era5_lon), u_2d, method="linear",
        bounds_error=False, fill_value=None,
    )
    iv = RegularGridInterpolator(
        (era5_lat, era5_lon), v_2d, method="linear",
        bounds_error=False, fill_value=None,
    )
    u_g = iu(pts).reshape(Ny, Nx)
    v_g = iv(pts).reshape(Ny, Nx)
    u_m = (u_g * angleCS + v_g * angleSN).astype(np.float32)
    v_m = (-u_g * angleSN + v_g * angleCS).astype(np.float32)
    return u_m, v_m


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------

def write_scalar_on_model_grid(ds, varname, output_path,
                                era5_lat, era5_lon, pts, Ny, Nx,
                                scale_factor=None):
    n_times = ds.sizes["valid_time"]
    with open(output_path, "wb") as f:
        for i in range(0, n_times, TIME_CHUNK):
            chunk = ds[varname].isel(valid_time=slice(i, i + TIME_CHUNK)).values
            if scale_factor is not None:
                chunk = chunk * scale_factor
            for k in range(chunk.shape[0]):
                out = interp_scalar_chunk(era5_lat, era5_lon, chunk[k], pts, Ny, Nx)
                out.astype(">f4").tofile(f)
            pct = 100.0 * min(i + chunk.shape[0], n_times) / n_times
            print(f"    {pct:.0f}%")


def write_wind_on_model_grid(ds_u, ds_v, out_u_path, out_v_path,
                              era5_lat, era5_lon, pts, Ny, Nx,
                              angleCS, angleSN):
    n_times = ds_u.sizes["valid_time"]
    with open(out_u_path, "wb") as fu, open(out_v_path, "wb") as fv:
        for i in range(0, n_times, TIME_CHUNK):
            u_chunk = ds_u["uwind"].isel(valid_time=slice(i, i + TIME_CHUNK)).values
            v_chunk = ds_v["vwind"].isel(valid_time=slice(i, i + TIME_CHUNK)).values
            for k in range(u_chunk.shape[0]):
                u_m, v_m = interp_and_rotate_wind_chunk(
                    era5_lat, era5_lon, u_chunk[k], v_chunk[k],
                    pts, Ny, Nx, angleCS, angleSN,
                )
                u_m.astype(">f4").tofile(fu)
                v_m.astype(">f4").tofile(fv)
            pct = 100.0 * min(i + u_chunk.shape[0], n_times) / n_times
            print(f"    {pct:.0f}%")


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

    # --- Model grid ---
    npx = config["domain"]["mpi"]["npx"]
    npy = config["domain"]["mpi"]["npy"]
    Nx = 96 * npx   # sNx * nPx
    Ny = 53 * npy   # sNy * nPy
    horizgridfile = os.path.join(simulation_input_dir, "horizgridfile.bin")

    print("Reading model grid...")
    xC, yC = read_model_grid(horizgridfile, Nx, Ny)
    angleCS, angleSN = compute_rotation_angles(xC, yC)
    print(f"  Grid: {Ny}x{Nx}, lon [{xC.min():.1f},{xC.max():.1f}], lat [{yC.min():.1f},{yC.max():.1f}]")
    print(f"  Rotation: angle [{np.rad2deg(np.arctan2(angleSN, angleCS)).min():.2f}, "
          f"{np.rad2deg(np.arctan2(angleSN, angleCS)).max():.2f}] deg")

    # ERA5 grid (after latitude flip: south-to-north)
    era5_lat = np.linspace(20.0, 60.0, 161)
    era5_lon = np.linspace(-90.0, -10.0, 321)
    pts = np.column_stack([yC.ravel(), xC.ravel()])

    # --- Process scalar variables ---
    written = set()
    for var in atm_vars:
        mitgcm_name = var["mitgcm_name"]
        if mitgcm_name in written or mitgcm_name in WIND_VARS:
            continue
        written.add(mitgcm_name)

        print(f"Processing {mitgcm_name}...")
        scale_factor = var.get("scale_factor")
        ds = _open_var(working_directory, prefix, mitgcm_name, years, t1, t2)
        output_path = os.path.join(simulation_input_dir, f"{mitgcm_name}.bin")
        write_scalar_on_model_grid(
            ds, mitgcm_name, output_path,
            era5_lat, era5_lon, pts, Ny, Nx,
            scale_factor=scale_factor,
        )
        ds.close()

    # --- Process wind vector (interpolate + rotate) ---
    print("Processing uwind + vwind (vector interpolation + rotation)...")
    ds_u = _open_var(working_directory, prefix, "uwind", years, t1, t2)
    ds_v = _open_var(working_directory, prefix, "vwind", years, t1, t2)
    write_wind_on_model_grid(
        ds_u, ds_v,
        os.path.join(simulation_input_dir, "uwind.bin"),
        os.path.join(simulation_input_dir, "vwind.bin"),
        era5_lat, era5_lon, pts, Ny, Nx,
        angleCS, angleSN,
    )
    ds_u.close()
    ds_v.close()

    # --- Computed variables (aqh from d2m + sp) ---
    for cv in computed_vars:
        mitgcm_name = cv["mitgcm_name"]
        print(f"Computing {mitgcm_name}...")
        ds_d2m = _open_var(working_directory, prefix, "d2m", years, t1, t2)
        ds_sp = _open_var(working_directory, prefix, "sp", years, t1, t2)
        n_times = ds_d2m.sizes["valid_time"]

        output_path = os.path.join(simulation_input_dir, f"{mitgcm_name}.bin")
        with open(output_path, "wb") as f:
            for i in range(0, n_times, TIME_CHUNK):
                d2m_k = ds_d2m["d2m"].isel(valid_time=slice(i, i + TIME_CHUNK)).values
                sp_pa = ds_sp["sp"].isel(valid_time=slice(i, i + TIME_CHUNK)).values
                aqh_era = np.array(
                    specific_humidity_from_dewpoint(
                        sp_pa * units.Pa, (d2m_k - 273.15) * units.degC
                    )
                )
                for k in range(aqh_era.shape[0]):
                    out = interp_scalar_chunk(
                        era5_lat, era5_lon, aqh_era[k], pts, Ny, Nx,
                    )
                    out.astype(">f4").tofile(f)
                pct = 100.0 * min(i + aqh_era.shape[0], n_times) / n_times
                print(f"    {pct:.0f}%")

        ds_d2m.close()
        ds_sp.close()

    print("Done — all EXF fields written on model grid.")


if __name__ == "__main__":
    main()
