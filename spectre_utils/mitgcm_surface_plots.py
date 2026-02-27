#!/usr/bin/env python

import os
from pathlib import Path
import numpy as np
import xmitgcm
import xarray as xr
from spectre_utils import common
import yaml
import matplotlib.pyplot as plt

def _has(obj, name):
    return (name in obj) or (name in getattr(obj, "coords", {})) or (name in getattr(obj, "data_vars", {}))

def _get(ds, name):
    if name in ds:
        return ds[name]
    if name in ds.coords:
        return ds.coords[name]
    if name in ds.data_vars:
        return ds.data_vars[name]
    raise KeyError(name)

def _surface_k_index(ds, var_name="T"):
    """
    Determine the surface k-index using any available vertical coordinate.
    Priority: RC, Z, Zp1, Depth. If none exist, return 0.
    """
    cand = [n for n in ["RC", "Z", "Zp1", "Depth", "depth"] if _has(ds, n)]
    if not cand:
        # try on the variable itself (sometimes attached there)
        v = ds[var_name]
        for n in ["RC", "Z", "Zp1", "Depth", "depth"]:
            if n in v.coords:
                cand = [n]
                break
    if not cand:
        return 0
    z = _get(ds, cand[0])
    # If z is 1D over k, pick the index closest to 0 (surface)
    if z.ndim == 1:
        k_idx = int(np.abs(z.values - 0.0).argmin())
        return k_idx
    # If z is 3D or something unusual, just default to first level
    return 0

def _robust_clim(da, q=0.995):
    """Compute robust color limits using quantiles, avoiding NaNs."""
    v = da.where(np.isfinite(da))
    lo = v.quantile(1 - q)
    hi = v.quantile(q)
    # bring to python floats (may be dask scalars)
    lo = float(lo.compute()) if hasattr(lo, "compute") else float(lo)
    hi = float(hi.compute()) if hasattr(hi, "compute") else float(hi)
    if not np.isfinite(lo) or not np.isfinite(hi) or lo == hi:
        # fallback to min/max
        lo = float(v.min().compute())
        hi = float(v.max().compute())
        if lo == hi:
            lo, hi = lo - 1, hi + 1
    return lo, hi

def plot_surface_fields(ds: xr.Dataset, outdir="frames_eps", dpi=200, rasterized=True):
    """
    Create EPS frames for:
      - T (surface)
      - S (surface)
      - Eta (free surface height)
    """
    outdir = Path(outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # ---- required names based on your dump ----
    time_name = "time"
    j_name, i_name = "j", "i"
    k_name = "k"
    lon_name, lat_name = "XC", "YC"   # 2-D (j,i)
    T_name = "T"
    S_name = "S"
    Eta_name = "Eta" if "Eta" in ds else ("ETAN" if "ETAN" in ds else "Eta")

    # pull static 2-D coords to numpy once
    Lon = ds[lon_name].compute().values  # (j,i)
    Lat = ds[lat_name].compute().values  # (j,i)

    # optional land mask
    mask = None
    if "maskInC" in ds:
        mask = ds["maskInC"].compute().values  # bool (j,i)

    # choose surface index
    k_sfc = _surface_k_index(ds, var_name=T_name)

    # build surface slices lazily (time, j, i)
    T_sfc = ds[T_name].isel({k_name: k_sfc})
    S_sfc = ds[S_name].isel({k_name: k_sfc})
    Eta   = ds[Eta_name]  # already (time, j, i)

    # precompute robust color limits (avoid doing per-frame)
    T_lo, T_hi   = _robust_clim(T_sfc)
    S_lo, S_hi   = _robust_clim(S_sfc)
    Eta_lo, Eta_hi = _robust_clim(Eta)

    def _fname(var, tval):
        # tval could be numpy.datetime64 or cftime
        try:
            ts = np.datetime_as_string(np.datetime64(tval, "s"), unit="s")
        except Exception:
            ts = str(tval)
        ts = ts.replace("-", "").replace(":", "").replace(" ", "T")
        return outdir / f"{var}_{ts}.eps"

    def _draw_frame(field2d, vmin, vmax, title, units, outpath):
        # compute only this frame to a numpy array
        A = field2d.values  # may still be dask
        A = field2d.compute().values if hasattr(field2d, "compute") else A
        if mask is not None:
            # mask out land (False -> NaN)
            A = np.where(mask, A, np.nan)

        plt.figure(figsize=(8, 6))
        # rasterized=True helps keep EPS size reasonable on large grids
        plt.pcolormesh(Lon, Lat, A, shading="auto", vmin=vmin, vmax=vmax,
                       rasterized=rasterized)
        plt.xlabel("Longitude")
        plt.ylabel("Latitude")
        cb = plt.colorbar()
        cb.set_label(units)
        plt.title(title)
        plt.tight_layout()
        plt.savefig(outpath, format="eps", dpi=dpi)
        plt.close()

    times = ds[time_name].values
    for it in range(len(times)):
        tval = times[it]

        Ti = T_sfc.isel({time_name: it})
        Si = S_sfc.isel({time_name: it})
        Ei = Eta.isel({time_name: it})

        # labels
        tlabel = str(np.array(tval)).split(".")[0]
        Tunits = Ti.attrs.get("units", "arb.")
        Sunits = Si.attrs.get("units", "arb.")
        Eunits = Ei.attrs.get("units", "arb.")

        _draw_frame(
            Ti, T_lo, T_hi,
            f"Surface Temperature @ {tlabel}",
            Tunits,
            _fname("T", tval),
        )
        _draw_frame(
            Si, S_lo, S_hi,
            f"Surface Salinity @ {tlabel}",
            Sunits,
            _fname("S", tval),
        )
        _draw_frame(
            Ei, Eta_lo, Eta_hi,
            f"Free Surface Height @ {tlabel}",
            Eunits,
            _fname("Eta", tval),
        )

    print(f"EPS frames written to {outdir.resolve()} (k_surface={k_sfc})")

def get_dataset(simulation_directory, model_delta_t, model_ref_date=None):
    return xmitgcm.open_mdsdataset(simulation_directory, 
                            grid_dir=simulation_directory, 
                            iters='all', 
                            prefix=['U', 'V', 'T', 'S', 'Eta'], 
                            read_grid=True, 
                            delta_t=model_delta_t,
                            ref_date=model_ref_date, 
                            geometry='curvilinear')


def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    simulation_directory = config['simulation_directory']
    model_delta_t = 120 # TO DO : Read this from the simulation directory input/data file 
    #model_delta_t = 450 # TO DO : Read this from the simulation directory input/data file 
    model_ref_date = config['domain']['time']['start']

    ds = get_dataset(f"{simulation_directory}", model_delta_t, model_ref_date=model_ref_date)
    print(ds.T)
    print(ds.dims)
    plot_surface_fields(ds, outdir=os.path.join(simulation_directory, "frames_eps"))

if __name__ == "__main__": 
    main()
