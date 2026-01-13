import numpy as np
import pandas as pd
import xarray as xr
import yaml
import os
from spectre_utils import common
import xgcm
import matplotlib.pyplot as plt


staticsmap = {
        'mask':'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1/glorys12v1-pgnstatics/PSY4V3R1_mask.nc',
        'mesh_hgr':'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1/glorys12v1-pgnstatics/PSY4V3R1_mesh_hgr.nc',
        'mesh_zgr':'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1/glorys12v1-pgnstatics/PSY4V3R1_mesh_zgr.nc',
        'bathymetry':'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1/glorys12v1-pgnstatics/PSY4V3R1_ORCA12_bathymetry.nc'
}

datamap = {
        'T': 'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridT',
        'S': 'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridS',
        'U': 'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridU',
        'V': 'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridV',
        'W': 'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridW',
        'KZ': 'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridKZ',
        'grid2D': 'dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-grid2D',
    }
def get_glorys12_statics(xmin, xmax, ymin, ymax, var):
    import xarray as xr

    datasets = {}
    url = staticsmap[var]
    print(f"Downloading from {url}")
    ds = xr.open_dataset(url,engine='pydap')

    region = (ds.nav_lon > xmin) & (ds.nav_lon < xmax) & (ds.nav_lat > ymin) & (ds.nav_lat < ymax)
    indices = np.argwhere(region.values)
    imin = min(indices[:,1])
    imax = max(indices[:,1])
    jmin = min(indices[:,0])
    jmax = max(indices[:,0])
    print(f"Extracting data for lon: {xmin} to {xmax}, lat: {ymin} to {ymax}")
    try:
        ds_subdomain = ds.isel({'x':slice(imin,imax),'y':slice(jmin,jmax)})
    except:
        ds_subdomain = ds.isel({'X':slice(imin,imax),'Y':slice(jmin,jmax)})

    print(ds_subdomain)
    return ds_subdomain

def get_glorys12_data(daterange, xmin, xmax, ymin, ymax, var):
    import xarray as xr

    datasets = {}
    ds = xr.open_dataset(datamap[var])

    region = (ds.nav_lon > xmin) & (ds.nav_lon < xmax) & (ds.nav_lat > ymin) & (ds.nav_lat < ymax)
    indices = np.argwhere(region.values)
    imin = min(indices[:,1])
    imax = max(indices[:,1])
    jmin = min(indices[:,0])
    jmax = max(indices[:,0])
    print(f"Extracting data for lon: {xmin} to {xmax}, lat: {ymin} to {ymax}")
    print(f"Time date range for data selection is : {daterange}")
    ds_subdomain = ds.isel({'x':slice(imin,imax),'y':slice(jmin,jmax)}).sel({'time_counter':daterange})
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

    ldate = pd.date_range(start=start_date, end=end_date, freq='D')
    ldate = ldate + pd.to_timedelta(12, unit='h')  # Shift to middle of the day, consistent with glorys output timestamp

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    #for var in staticsmap.keys():
    #  ds = get_glorys12_statics(
    #      xmin=min_long,
    #      xmax=max_long,
    #      ymin=min_lat,
    #      ymax=max_lat,
    #      var=var)
    #  ds.to_netcdf(os.path.join(working_directory, f"{dataset_prefix}_{var}_glorys12_raw.static.nc"))


    download_chunk_days = 10
    chunk = 0
    for start in range(0,len(ldate),download_chunk_days):
      end = min(start+download_chunk_days,len(ldate))
      date_range = ldate[start:end]
      print(f"Chunk {chunk} : {date_range[0]} to {date_range[-1]}")
      chunk+=1
      for var in datamap.keys():
        ds = get_glorys12_data(
            daterange=date_range,
            xmin=min_long,
            xmax=max_long,
            ymin=min_lat,
            ymax=max_lat,
            var=var)

        ds.to_netcdf(os.path.join(working_directory, f"{dataset_prefix}_{var}_glorys12_raw.{chunk}.nc"))


if __name__ == "__main__":
    main()

    #datapgn = xr.open_dataset('dap2://tds.mercator-ocean.fr/thredds/dodsC/glorys12v1-daily-gridT')
    #lon_min = -10
    #lon_max = 0
    #lat_min = 42
    #lat_max = 52
    #geotest = (datapgn.nav_lon > lon_min) & (datapgn.nav_lon < lon_max) & (datapgn.nav_lat > lat_min) & (datapgn.nav_lat < lat_max)
    #geoindex = np.argwhere(geotest.values)
    #xmin = min(geoindex[:,1])
    #xmax = max(geoindex[:,1])
    #ymin = min(geoindex[:,0])
    #ymax = max(geoindex[:,0])
    #ldate = pd.date_range(start="20150301",end="20150307",freq="D") # all monday between start and end
    #ldate = ldate + pd.to_timedelta(12, unit='H')  # Shift to middle of the day, consistent with glorys output timestamp
    ##biscay = datapgn.isel({'x':slice(xmin,xmax),'y':slice(ymin,ymax)}).sel(deptht=[0,5,50,500],method='nearest').sel({'time_counter':ldate},method="nearest") # fails with "ValueError: index must be monotonic increasing or decreasing"
    #biscay = datapgn.isel({'x':slice(xmin,xmax),'y':slice(ymin,ymax)}).sel(deptht=[0,5,50,500],method='nearest').sel({'time_counter':ldate})
    #print(biscay.dims)
    #biscay.to_netcdf("test.nc")
