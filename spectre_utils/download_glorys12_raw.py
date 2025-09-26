import numpy as np
import pandas as pd
import xarray as xr
import yaml
import os
from spectre_utils import common
import xgcm
import matplotlib.pyplot as plt


def get_glorys12_data(start_date, end_date, xmin, xmax, ymin, ymax):
    import xarray as xr

    ds = xr.open_dataset('dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridT')
    ldate = pd.date_range(start=start_date, end=end_date, freq='D')

    region = (ds.nav_lon > xmin) & (ds.nav_lon < xmax) & (ds.nav_lat > ymin) & (ds.nav_lat < ymax)
    indices = np.argwhere(region.values)
    xmin = min(indices[:,1])
    xmax = max(indices[:,1])
    ymin = min(indices[:,0])
    ymax = max(indices[:,0])
    print(f"Extracting data for lon: {xmin} to {xmax}, lat: {ymin} to {ymax}")
    ds_subdomain = ds.isel({'x':slice(xmin,xmax),'y':slice(ymin,ymax)}).sel({'time_counter':ldate},method="nearest")

    print(ds_subdomain)
    return ds_subdomain

def main():
        
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    # Get time range from configuration
    time_range = config.get('domain').get('time')
    start_date = time_range.get('start')
    end_date = time_range.get('end')
    longitude_range = config.get('domain').get('longitude')
    min_long = longitude_range.get('min')
    max_long = longitude_range.get('max')
    latitude_range = config.get('domain').get('latitude')
    min_lat = latitude_range.get('min')
    max_lat = latitude_range.get('max')
    working_directory = config.get('working_directory', '.')
    dataset_prefix = config.get('ocean').get('prefix')
    
    ds = get_glorys12_data(
        start_date=start_date,
        end_date=end_date,
        xmin=min_long,
        xmax=max_long,
        ymin=min_lat,
        ymax=max_lat
    )

    #ds.to_netcdf(os.path.join(working_directory, f"{dataset_prefix}_glorys12_raw.nc"))

    ds.votemper[0,:,-1,:].squeeze().plot(vmax=2,vmin=-2)
    plt.savefig('test.png')

if __name__ == "__main__":
    main()
