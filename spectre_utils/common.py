#!/usr/bin/env python3
import sys


def cli():
    import argparse
    # Get configuration file from command line
    parser = argparse.ArgumentParser(description="Download Copernicus Marine data for a specific date range.")
    parser.add_argument('config_file', type=str, help="Path to the configuration file.")
    return parser.parse_args()

def copernicus_filename(working_directory, dataset_prefix, start_date):
    """Construct the filename for the Copernicus dataset based on the working directory, prefix, and start date."""
    import os
    return os.path.join(working_directory, f"{dataset_prefix}_{start_date}.nc")

def from_copernicus(dataset_id, variables, start_date, end_date, min_long, max_long, min_lat, max_lat, min_depth=0, max_depth=6000, working_directory='.', dataset_prefix='copernicus_marine'):
    """Download data from Copernicus Marine and return the dataset and grid."""
    import copernicusmarine
    import xarray as xr
    import xgcm
    from xgcm.autogenerate import generate_grid_ds
    import os

    filename = copernicus_filename(working_directory, dataset_prefix, start_date)
    if not os.path.exists(filename):
        print(f"Downloading data for {dataset_id} from {start_date} to {end_date}...")
        copernicusmarine.subset(
            dataset_id=dataset_id,
            variables=variables,
            minimum_longitude=min_long,
            maximum_longitude=max_long,
            minimum_latitude=min_lat,
            maximum_latitude=max_lat,
            minimum_depth=min_depth,
            maximum_depth=max_depth,
            start_datetime=start_date,
            end_datetime=end_date,
            output_filename=filename,
            output_directory=working_directory,
        )
    else:
        print(f"Using existing data file: {filename}")
    
    ds = xr.open_dataset(copernicus_filename(working_directory, dataset_prefix, start_date))

    ds = ds.rename({
    'longitude': 'xc',
    'latitude': 'yc',
    'depth': 'zc'
   })

    ds_full = generate_grid_ds(ds, {'X':'xc', 'Y':'yc'})
    ds_full = ds_full.rename({'xc_left': 'xg', 'yc_left': 'yg'})
    
    if 'time' in ds_full:
        grid = xgcm.Grid(ds_full, coords={
        'X': {'center': 'xc', 'right': 'xg'},
        'Y': {'center': 'yc', 'right': 'yg'},
        'Z': {'center': 'zc'},
        'T': {'center': 'time'}})
    else:
        grid = xgcm.Grid(ds_full, coords={
        'X': {'center': 'xc', 'right': 'xg'},
        'Y': {'center': 'yc', 'right': 'yg'},
        'Z': {'center': 'zc'}})

    return ds_full, grid


def load_atm_dataset(working_directory, prefix, years, atm_vars, t1, t2):
    """Load ERA5 atmospheric variables per MITgcm name, rename, and apply optional scale factors.

    Each variable's files are loaded separately so that the single data variable
    in each netCDF can be renamed to its ``mitgcm_name`` and any ``scale_factor``
    from the config can be applied before the variables are merged.
    Duplicate ``mitgcm_name`` entries (e.g. from config copy-paste) are skipped.
    """
    import xarray as xr

    seen = set()
    sub_datasets = []
    for var in atm_vars:
        mitgcm_name = var["mitgcm_name"]
        if mitgcm_name in seen:
            continue
        seen.add(mitgcm_name)

        scale_factor = var.get("scale_factor")
        files = [f"{working_directory}/{prefix}_{mitgcm_name}_{year}.nc" for year in years]
        for f in files:
            import os
            if not os.path.exists(f):
                print(f"Missing file: {f}", file=sys.stderr)
                sys.exit(1)

        sub_ds = xr.open_mfdataset(files, combine="by_coords", parallel=True).sel(
            valid_time=slice(t1, t2)
        )
        data_vars = list(sub_ds.data_vars)
        if len(data_vars) == 1 and data_vars[0] != mitgcm_name:
            sub_ds = sub_ds.rename({data_vars[0]: mitgcm_name})
        if scale_factor is not None:
            sub_ds[mitgcm_name] = sub_ds[mitgcm_name] * scale_factor
        sub_datasets.append(sub_ds)

    return xr.merge(sub_datasets)
