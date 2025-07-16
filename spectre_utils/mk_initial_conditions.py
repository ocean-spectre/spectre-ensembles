import copernicusmarine
from datetime import date, timedelta
import yaml
import os
import json
import xarray as xr
import xgcm
from spectre_utils import common

# def cli():
#     import argparse
#     # Get configuration file from command line
#     parser = argparse.ArgumentParser(description="Download Copernicus Marine data for a specific date range.")
#     parser.add_argument('config_file', type=str, help="Path to the configuration file.")
#     return parser.parse_args()

def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    print(json.dumps(config, indent=2))
    # Get time range from configuration
    time_range = config.get('domain').get('time')
    start_date = time_range.get('start')
    end_date = time_range.get('end')
    dataset_id = config.get('dataset_id')
    longitude_range = config.get('domain').get('longitude')
    min_long = longitude_range.get('min')
    max_long = longitude_range.get('max')
    latitude_range = config.get('domain').get('latitude')
    min_lat = latitude_range.get('min')
    max_lat = latitude_range.get('max')
    working_directory = config.get('working_directory', '.')
    dataset_prefix = config.get('dataset_prefix', 'copernicus_marine')
    min_depth = config.get('domain').get('depth', {}).get('min', 0)
    max_depth = config.get('domain').get('depth', {}).get('max', 6000)

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    # Get the initial conditions
    ds, grid = common.from_copernicus(
        dataset_id=dataset_id,
        start_date=start_date,
        end_date=start_date,
        min_long=min_long,
        max_long=max_long,
        min_lat=min_lat,
        max_lat=max_lat,
        min_depth=min_depth,
        max_depth=max_depth,
        working_directory=working_directory,
        dataset_prefix=dataset_prefix
    )

#     copernicusmarine.subset(
#         dataset_id=dataset_id,
#         variables=[
#             "thetao",  # Sea water potential temperature
#             "so",  # Sea water salinity
#             "uo",  # Eastward ocean current velocity
#             "vo",  # Northward sea water velocity
#             "zos",  # Sea Surface Height above Geoid
#         ],
#         minimum_longitude=min_long,
#         maximum_longitude=max_long,
#         minimum_latitude=min_lat,
#         maximum_latitude=max_lat,
#         minimum_depth=min_depth,
#         maximum_depth=max_depth,
#         start_datetime=start_date,
#         end_datetime=start_date,
#         output_filename=f"{dataset_prefix}_{start_date}.nc",
#         output_directory=working_directory,
#     )

#     ds = xr.open_dataset(f"{working_directory}/{dataset_prefix}_{start_date}.nc")
#     ds = ds.rename({
#     'longitude': 'xc',
#     'latitude': 'yc',
#     'depth': 'zc'
#    })
#     ds.coords['xg'] = xr.DataArray(
#         0.5 * (ds.xc[:-1].values + ds.xc[1:].values),
#         dims='xg'
#     )
#     ds.coords['yg'] = xr.DataArray(
#         0.5 * (ds.yc[:-1].values + ds.yc[1:].values),
#         dims='yg'
#     )
    print(ds)
    
    # grid = xgcm.Grid(ds, coords={
    # 'X': {'center': 'xc', 'right': 'xg'},
    # 'Y': {'center': 'yc', 'right': 'yg'},
    # 'Z': {'center': 'zc'},
    # 'T': {'center': 'time'}})
    print(grid)

if __name__ == "__main__":
    main()