#!/usr/bin/env python3


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

def from_copernicus(dataset_id, start_date, end_date, min_long, max_long, min_lat, max_lat, min_depth=0, max_depth=6000, working_directory='.', dataset_prefix='copernicus_marine'):
    """Download data from Copernicus Marine and return the dataset and grid."""
    import copernicusmarine
    import xarray as xr
    import xgcm
    import os

    filename = copernicus_filename(working_directory, dataset_prefix, start_date)
    if not os.path.exists(filename):
        print(f"Downloading data for {dataset_id} from {start_date} to {end_date}...")
        copernicusmarine.subset(
            dataset_id=dataset_id,
            variables=[
                "thetao",  # Sea water potential temperature
                "so",  # Sea water salinity
                "uo",  # Eastward ocean current velocity
                "vo",  # Northward sea water velocity
                "zos",  # Sea Surface Height above Geoid
            ],
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
    
    #ds = xr.open_dataset(f"{working_directory}/{dataset_prefix}_{start_date}.nc")
    ds = xr.open_dataset(copernicus_filename(working_directory, dataset_prefix, start_date))

    ds = ds.rename({
    'longitude': 'xc',
    'latitude': 'yc',
    'depth': 'zc'
   })
    ds.coords['xg'] = xr.DataArray(
        0.5 * (ds.xc[:-1].values + ds.xc[1:].values),
        dims='xg'
    )
    ds.coords['yg'] = xr.DataArray(
        0.5 * (ds.yc[:-1].values + ds.yc[1:].values),
        dims='yg'
    )
    
    grid = xgcm.Grid(ds, coords={
    'X': {'center': 'xc', 'right': 'xg'},
    'Y': {'center': 'yc', 'right': 'yg'},
    'Z': {'center': 'zc'},
    'T': {'center': 'time'}})

    return ds, grid
