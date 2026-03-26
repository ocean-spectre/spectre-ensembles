"""
mk_exf_wind_on_model_grid.py
=============================
Pre-interpolate ERA5 u/v winds from the regular 0.25° lat-lon grid to the
curvilinear model grid and rotate from geographic (east/north) to model-grid
(i/j) coordinates.

This bypasses MITgcm's EXF_INTERP_UV, which produces spurious extreme wind
values on this curvilinear grid.

Outputs:
    input/uwind_modelgrid.bin  — u-wind in model i-direction (big-endian f32)
    input/vwind_modelgrid.bin  — v-wind in model j-direction (big-endian f32)

After running, update data.exf:
    uwindfile = 'uwind_modelgrid.bin'
    vwindfile = 'vwind_modelgrid.bin'
    Remove uwind_nlon/nlat/lon0/lat0/lon_inc/lat_inc from EXF_NML_04
    Remove vwind_nlon/nlat/lon0/lat0/lon_inc/lat_inc from EXF_NML_04
    Set rotateStressOnAgrid = .FALSE.
"""

import os
import sys
import numpy as np
import xarray as xr
import yaml
from datetime import datetime
from scipy.interpolate import RegularGridInterpolator
from spectre_utils import common

TIME_CHUNK = 744


def read_model_grid(horizgridfile, Nx, Ny):
    """Read xC, yC from the MITgcm curvilinear horizgridfile (big-endian f64)."""
    arr = np.fromfile(horizgridfile, dtype=">f8")
    fields = arr.reshape(16, Ny + 1, Nx + 1)
    xC = fields[0, :Ny, :Nx]
    yC = fields[1, :Ny, :Nx]
    return xC, yC


def compute_rotation_angles(xC, yC):
    """Compute angleCS, angleSN from the i-direction of the curvilinear grid.

    θ = atan2(Δlat, Δlon * cos(lat))  where differences are along the i-axis.
    """
    dlon = np.empty_like(xC)
    dlat = np.empty_like(yC)
    # Centered differences in the interior
    dlon[:, 1:-1] = xC[:, 2:] - xC[:, :-2]
    dlat[:, 1:-1] = yC[:, 2:] - yC[:, :-2]
    # Forward/backward at edges
    dlon[:, 0] = xC[:, 1] - xC[:, 0]
    dlat[:, 0] = yC[:, 1] - yC[:, 0]
    dlon[:, -1] = xC[:, -1] - xC[:, -2]
    dlat[:, -1] = yC[:, -1] - yC[:, -2]

    cos_lat = np.cos(np.deg2rad(yC))
    angle = np.arctan2(dlat, dlon * cos_lat)
    return np.cos(angle), np.sin(angle)


def build_interpolators(era5_lat, era5_lon, u_data, v_data):
    """Build RegularGridInterpolator objects for u and v."""
    interp_u = RegularGridInterpolator(
        (era5_lat, era5_lon), u_data, method="linear", bounds_error=False, fill_value=None
    )
    interp_v = RegularGridInterpolator(
        (era5_lat, era5_lon), v_data, method="linear", bounds_error=False, fill_value=None
    )
    return interp_u, interp_v


def main():
    args = common.cli()
    with open(args.config_file, "r") as f:
        config = yaml.safe_load(f)

    simulation_dir = config["simulation_directory"]
    input_dir = os.path.join(simulation_dir, "input")

    # Model grid dimensions
    npx = config["domain"]["mpi"]["npx"]
    npy = config["domain"]["mpi"]["npy"]
    # SIZE.h: sNx=96, sNy=53
    Nx = 96 * npx  # 768
    Ny = 53 * npy  # 424

    # Read model grid
    horizgridfile = os.path.join(input_dir, "horizgridfile.bin")
    print(f"Reading model grid from {horizgridfile}")
    xC, yC = read_model_grid(horizgridfile, Nx, Ny)
    print(f"  Model grid: {Ny}x{Nx}, lon [{xC.min():.2f}, {xC.max():.2f}], lat [{yC.min():.2f}, {yC.max():.2f}]")

    # Compute rotation angles
    angleCS, angleSN = compute_rotation_angles(xC, yC)
    print(f"  Rotation angles: CS [{angleCS.min():.6f}, {angleCS.max():.6f}], SN [{angleSN.min():.6f}, {angleSN.max():.6f}]")

    # ERA5 grid (after latitude flip: south-to-north)
    NY_ERA, NX_ERA = 161, 321
    era5_lat = np.linspace(20.0, 60.0, NY_ERA)  # south-to-north
    era5_lon = np.linspace(-90.0, -10.0, NX_ERA)

    # Model grid points for interpolation (flattened, then reshaped after)
    pts = np.column_stack([yC.ravel(), xC.ravel()])

    # ERA5 binary paths
    uwind_path = os.path.join(input_dir, "uwind.bin")
    vwind_path = os.path.join(input_dir, "vwind.bin")

    # Count records
    uwind_size = os.path.getsize(uwind_path)
    nt = uwind_size // (NY_ERA * NX_ERA * 4)
    print(f"  ERA5 records: {nt}")

    # Output paths
    out_u = os.path.join(input_dir, "uwind_modelgrid.bin")
    out_v = os.path.join(input_dir, "vwind_modelgrid.bin")

    rec_size = NY_ERA * NX_ERA
    model_size = Ny * Nx

    print(f"Interpolating and rotating {nt} records...")
    with open(uwind_path, "rb") as fu_in, \
         open(vwind_path, "rb") as fv_in, \
         open(out_u, "wb") as fu_out, \
         open(out_v, "wb") as fv_out:

        for t in range(0, nt, TIME_CHUNK):
            n = min(TIME_CHUNK, nt - t)
            u_era = np.fromfile(fu_in, dtype=">f4", count=n * rec_size).reshape(n, NY_ERA, NX_ERA)
            v_era = np.fromfile(fv_in, dtype=">f4", count=n * rec_size).reshape(n, NY_ERA, NX_ERA)

            u_out = np.empty((n, Ny, Nx), dtype=np.float32)
            v_out = np.empty((n, Ny, Nx), dtype=np.float32)

            for k in range(n):
                # Bilinear interpolation to model grid
                interp_u, interp_v = build_interpolators(era5_lat, era5_lon, u_era[k], v_era[k])
                u_interp = interp_u(pts).reshape(Ny, Nx)
                v_interp = interp_v(pts).reshape(Ny, Nx)

                # Rotate from geographic (east, north) to model grid (i, j)
                u_out[k] = u_interp * angleCS + v_interp * angleSN
                v_out[k] = -u_interp * angleSN + v_interp * angleCS

            u_out.astype(">f4").tofile(fu_out)
            v_out.astype(">f4").tofile(fv_out)

            pct = 100.0 * min(t + n, nt) / nt
            print(f"  {pct:.0f}% ({t + n}/{nt} records)")

    print(f"Done. Output:")
    print(f"  {out_u}")
    print(f"  {out_v}")


if __name__ == "__main__":
    main()
