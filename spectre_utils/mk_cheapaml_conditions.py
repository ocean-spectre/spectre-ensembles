import cdsapi
import os
from spectre_utils import common
import yaml
import numpy as np
import sys
import xarray as xr
from metpy.calc import specific_humidity_from_dewpoint
from metpy.units import units
from datetime import datetime, timedelta
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.animation import FFMpegWriter

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
    """
    Create an MP4 animation of ds[var] over the 'valid_time' dimension.

    Parameters
    ----------
    ds : xarray.Dataset
        Dataset containing the DataArray (e.g., 't2m', 'u10', etc.) with
        dims ('valid_time', 'latitude', 'longitude').
    var : str
        Variable name to animate.
    out_path : str
        Output MP4 filename.
    fps : int
        Frames per second.
    cmap : str
        Matplotlib colormap name.
    vmin, vmax : float or None
        Color limits. If None, they’re computed (robust percentiles if robust=True).
    robust : bool
        If True, use 2–98 percentiles for color limits to avoid outliers.
    dpi : int
        DPI for the saved video frames.
    title : str or None
        Optional title prefix. If None, uses the variable name and units.
    """
    da = ds[var]
    if "valid_time" not in da.dims:
        raise ValueError(f"{var} must have a 'valid_time' dimension.")

    # Choose color limits if not provided (use small sample to keep it quick with dask)
    if vmin is None or vmax is None:
        if robust:
            q = da.isel(valid_time=slice(0, max(1, min(5, da.sizes["valid_time"]))))
            # Flatten spatial dims and compute robust quantiles
            lo, hi = q.quantile([0.02, 0.98], dim=("valid_time", "latitude", "longitude")).compute().values
            vmin = lo if vmin is None else vmin
            vmax = hi if vmax is None else vmax
        else:
            vmin = da.min().compute().item() if vmin is None else vmin
            vmax = da.max().compute().item() if vmax is None else vmax
        if vmin == vmax:
            # Avoid degenerate color scale
            eps = 1e-6 if vmin == 0 else abs(vmin) * 1e-3
            vmin, vmax = vmin - eps, vmax + eps

    # Get coordinates (supports 1-D or 2-D lat/lon)
    lat = da.coords.get("latitude")
    lon = da.coords.get("longitude")
    if lat is None or lon is None:
        raise ValueError("Expected 'latitude' and 'longitude' coordinates.")

    if lat.ndim == 1 and lon.ndim == 1:
        X, Y = np.meshgrid(lon.values, lat.values)
        is_structured = True
    else:
        X, Y = lon.values, lat.values
        is_structured = False

    # Prepare figure
    fig, ax = plt.subplots(figsize=(8, 5), dpi=dpi)
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")

    # First frame (compute only one slice)
    frame0 = da.isel(valid_time=0).compute()
    if is_structured:
        mappable = ax.pcolormesh(X, Y, frame0, shading="auto", vmin=vmin, vmax=vmax, cmap=cmap)
    else:
        # For curvilinear grids, pcolormesh with 2-D X/Y
        mappable = ax.pcolormesh(X, Y, frame0, shading="auto", vmin=vmin, vmax=vmax, cmap=cmap)

    cbar = fig.colorbar(mappable, ax=ax, pad=0.02)
    units = da.attrs.get("units", "")
    cbar.set_label(f"{var} [{units}]" if units else var)

    # Title template
    ttl_prefix = title if title is not None else f"{var} {('['+units+']') if units else ''}".strip()
    time_values = ds["valid_time"].values

    def set_title(i):
        tval = np.datetime_as_string(time_values[i], unit="m") if np.issubdtype(time_values.dtype, np.datetime64) else str(time_values[i])
        ax.set_title(f"{ttl_prefix}\nvalid_time: {tval}")

    set_title(0)

    writer = FFMpegWriter(fps=fps, metadata={"artist": "xarray/matplotlib"}, bitrate=-1)

    with writer.saving(fig, out_path, dpi):
        writer.grab_frame()
        # Remaining frames
        for i in range(1, da.sizes["valid_time"]):
            frame = da.isel(valid_time=i).compute()
            mappable.set_array(frame) #.ravel() if is_structured else frame.ravel())
            # A safer update for pcolormesh is to remove and redraw; but set_array works for QuadMesh.
            # If you ever see artifacts, uncomment the redraw block below and comment set_array above:
            # for coll in ax.collections:
            #     coll.remove()
            # mappable = ax.pcolormesh(X, Y, frame, shading="auto", vmin=vmin, vmax=vmax, cmap=cmap)
            set_title(i)
            writer.grab_frame()

    plt.close(fig)
    return out_path

def main():

    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    working_directory = config['working_directory']
    simulation_directory = config['simulation_directory']
    years= config['atmosphere']['years']
    vars= config['atmosphere']['variables']
    prefix = config['atmosphere']['prefix']

    # Load in the xc,yc grid from the simulation directory
    simulation_input_dir = os.path.join(simulation_directory, 'input')
    with open(os.path.join(simulation_input_dir, 'xc.bin'), 'rb') as f:
        xc = np.fromfile(f, dtype='>f4')
    with open(os.path.join(simulation_input_dir, 'yc.bin'), 'rb') as f:
        yc = np.fromfile(f, dtype='>f4')

    t1 = datetime.strptime(config['domain']['time']['start'], "%Y-%m-%d")
    t2 = datetime.strptime(config['domain']['time']['end'], "%Y-%m-%d")


    # Time range
    # Load in the netcdf files for the era5 datafor var in vars.keys():
    era5_files = []
    for var in vars.keys():
        for year in years:
            target = f"{working_directory}/{prefix}_{vars[var]}_{year}.nc"
            if not os.path.exists(target):
                print(f"File {target} does not exist, go back and run download_era5.py")
                sys.exit(1)
            era5_files.append(target)

    # Load a multi-file dataset from the era5 files
    ds = xr.open_mfdataset(era5_files, combine='by_coords', parallel=True).sel(valid_time=slice(t1,t2))
    print(ds)

    # To do , interpolate all fields in the dataset to the xc,yc grid
    ds_interp = ds.interp(longitude=xc, latitude=yc, method='cubic')

    d2m = ds_interp["d2m"] - 273.15 # Convert from Kelvin to Celsius
    # Calculate specific humidity
    ds_interp['q'] = specific_humidity_from_dewpoint( ds_interp['msl']* units.Pa, d2m * units.degC) #.to('kg/kg')

    print(ds_interp)
    animations_dir = os.path.join(simulation_directory, 'animations')

    if not os.path.exists(animations_dir):
        os.makedirs(animations_dir)

    animate_variable(ds_interp, "u10", out_path=os.path.join(animations_dir, "u10.mp4"), fps=8, cmap="plasma")
    animate_variable(ds_interp, "v10", out_path=os.path.join(animations_dir, "v10.mp4"), fps=8, cmap="plasma")
    animate_variable(ds_interp, "t2m", out_path=os.path.join(animations_dir, "t2m.mp4"), fps=8, cmap="plasma")
    animate_variable(ds_interp, "d2m", out_path=os.path.join(animations_dir, "d2m.mp4"), fps=8, cmap="plasma")
    animate_variable(ds_interp, "q", out_path=os.path.join(animations_dir, "q.mp4"), fps=8, cmap="plasma")
    animate_variable(ds_interp, "avg_sdswrf", out_path=os.path.join(animations_dir, "avg_sdswrf.mp4"), fps=8, cmap="plasma")
    animate_variable(ds_interp, "avg_snlwrf", out_path=os.path.join(animations_dir, "avg_snlwrf.mp4"), fps=8, cmap="plasma")

    # # Write fields to binary files
    # with open(os.path.join(simulation_input_dir, 'u10.bin'), 'wb') as f:
    #     ds_interp['u10'].values.astype('>f4').tofile(f)

    # with open(os.path.join(simulation_input_dir, 'v10.bin'), 'wb') as f:
    #     ds_interp['v10'].values.astype('>f4').tofile(f)

    # with open(os.path.join(simulation_input_dir, 't2m.bin'), 'wb') as f:
    #     ds_interp['t2m'].values.astype('>f4').tofile(f)

    # with open(os.path.join(simulation_input_dir, 'q2m.bin'), 'wb') as f:
    #     ds_interp['q'].values.astype('>f4').tofile(f)

    # with open(os.path.join(simulation_input_dir, 'avg_sdswrf.bin'), 'wb') as f:
    #     ds_interp['avg_sdswrf'].values.astype('>f4').tofile(f)

    # with open(os.path.join(simulation_input_dir, 'avg_snlwrf.bin'), 'wb') as f:
    #     ds_interp['avg_snlwrf'].values.astype('>f4').tofile(f)

    # with open(os.path.join(simulation_input_dir, 'tp.bin'), 'wb') as f:
    #     ds_interp['tp'].values.astype('>f4').tofile(f)

    data_cheapaml = f"""
# cheapaml parameters
 &CHEAPAML_CONST
 cheapaml_ntim = 5,
 cheapaml_mask_width=5,
 cheapaml_h = 1000.0,
 cheapaml_kdiff = 1000.0,
# cheapaml_taurelax = 0.1,
# cheapaml_taurelaxocean = 0.0
 &end
# Forcing Files 
 &CHEAPAML_PARM01
 UWindFile='u10.box',
 VWindFile='v10.box',
 SolarFile='avg_sdswrf.box',
 TrFile='t2m.box',
 AirTempFile='t2m.box',
 QrFile='q2m.box',
 AirQFile='q2m.box',
 cheap_dlwfile='avg_snlwrf.box'
 cheap_prfile='tp.box'
 periodicExternalForcing_cheap=.TRUE.,
 externForcingPeriod_cheap=21600.0,
 externForcingCycle_cheap=31536000.0,
 &end
# Formulation parameters
 &CHEAPAML_PARM02
 useFreshWaterFlux=.TRUE.,
 FluxFormula='COARE3',
 useFluxLimit=.TRUE.,
 usetimevarblh=.FALSE.,
 useclouds=.FALSE.,
 usedlongwave=.TRUE.,
 usePrecip=.TRUE.,
 &end
"""
    
if __name__ == "__main__":
    main()