import yaml
import os
import xarray as xr
from spectre_utils import common
import xgcm

#def plot_boundary_cross_sections(ds, grid):
#def plot_vertical_grid(ds, grid):
def plot_surface_fields(ds, grid,working_directory='.'):
    """Plot surface fields from the dataset."""
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs

    fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
    p = ds['Eta'].isel(time=0).plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
    # show lat/lon grid
    gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                        linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
    gl.xlabels_top = False # Hide longitude labels at the top
    gl.ylabels_right = False # Hide latitude labels on the right    plt.title('Sea Surface Height')
    plt.savefig(os.path.join(working_directory, 'sea_surface_height.png'))

def plot_mask(ds, working_directory='.'):
    """Plot the mask from the dataset."""
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs

    fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
    p = ds['mask'][0,:,:].plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
    # show lat/lon grid
    gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                        linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
    gl.xlabels_top = False # Hide longitude labels at the top
    gl.ylabels_right = False # Hide latitude labels on the right

    #ax.coastlines()
    plt.title('Mask')
    plt.savefig(os.path.join(working_directory, 'mask.png'))

def plot_bathy(ds, working_directory='.'):
    """Plot the bathymetry from the dataset."""
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs

    fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
    p = ds['bathy'].plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
    # show lat/lon grid
    gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                        linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
    gl.xlabels_top = False # Hide longitude labels at the top
    gl.ylabels_right = False # Hide latitude labels on the right

    plt.title('Bathymetry')
    plt.savefig(os.path.join(working_directory, 'bathymetry.png'))

def plot_zbot(ds, working_directory='.'):
    """Plot the zbot from the dataset."""
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs

    fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
    p = ds['zbot'].plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
    # show lat/lon grid
    gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                        linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
    gl.xlabels_top = False # Hide longitude labels at the top
    gl.ylabels_right = False # Hide latitude labels on the right

    plt.title('Bottom cell layer')
    plt.savefig(os.path.join(working_directory, 'zbot.png'))

def get_initial_conditions(config):
    # Get time range from configuration
    time_range = config.get('domain').get('time')
    start_date = time_range.get('start')
    #end_date = time_range.get('end')
    dataset_id = config.get('ocean').get('dataset_id')
    ocean_variables = config.get('ocean').get('variables')
    longitude_range = config.get('domain').get('longitude')
    min_long = longitude_range.get('min')
    max_long = longitude_range.get('max')
    latitude_range = config.get('domain').get('latitude')
    min_lat = latitude_range.get('min')
    max_lat = latitude_range.get('max')
    working_directory = config.get('working_directory', '.')
    dataset_prefix = config.get('ocean').get('prefix')
    min_depth = config.get('domain').get('depth', {}).get('min', 0)
    max_depth = config.get('domain').get('depth', {}).get('max', 6000)

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    # Get the initial conditions
    ds, grid = common.from_copernicus(
        dataset_id=dataset_id,
        variables=ocean_variables,
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
    return ds, grid

def get_statics(config):
    # Get time range from configuration
    time_range = config.get('domain').get('time')
    start_date = time_range.get('start')
    #end_date = time_range.get('end')
    dataset_id = config.get('statics').get('dataset_id')
    ocean_variables = config.get('statics').get('variables')
    longitude_range = config.get('domain').get('longitude')
    min_long = longitude_range.get('min')
    max_long = longitude_range.get('max')
    latitude_range = config.get('domain').get('latitude')
    min_lat = latitude_range.get('min')
    max_lat = latitude_range.get('max')
    working_directory = config.get('working_directory', '.')
    dataset_prefix = config.get('statics').get('prefix')
    min_depth = config.get('domain').get('depth', {}).get('min', 0)
    max_depth = config.get('domain').get('depth', {}).get('max', 6000)

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    # Get the initial conditions
    ds, grid = common.from_copernicus(
        dataset_id=dataset_id,
        variables=ocean_variables,
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
    return ds, grid

def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    ds, grid = get_initial_conditions(config)
    ds_static, grid_static = get_statics(config)

    # Now, we need to interpolate to the c-grid locations
    U = grid.interp(ds['uo'],axis='X')[...,1:-1,1:-1]
    V = grid.interp(ds['vo'],axis='Y')[...,1:-1,1:-1]
    T = ds['thetao'][...,1:-1,1:-1]
    S = ds['so'][...,1:-1,1:-1]
    Eta = ds['zos'][...,1:-1,1:-1]
    mask = ds_static['mask'][...,1:-1,1:-1]
    zbot = ds_static['deptho_lev'][1:-1,1:-1]
    bathy = ds_static['deptho'][1:-1,1:-1]

    # create new dataset with interpolated variables
    ds_interp = xr.Dataset({
        'U': (['time', 'zc', 'yc', 'xg'], U.values),
        'V': (['time', 'zc', 'yg', 'xc'], V.values),
        'T': (['time', 'zc', 'yc', 'xc'], T.values),
        'S': (['time', 'zc', 'yc', 'xc'], S.values),
        'Eta': (['time', 'yc', 'xc'], Eta.values),
        'mask': (['zc', 'yc', 'xc'], mask.values),
        'zbot': (['yc', 'xc'], zbot.values),
        'bathy': (['yc', 'xc'], bathy.values)
    }, coords={
        'time': ds['time'],
        'zc': ds['zc'],
        'yc': ds['yc'][1:-1],
        'yg': ds['yg'][1:-1],
        'xc': ds['xc'][1:-1],
        'xg': ds['xg'][1:-1],
    })
    grid_interp = xgcm.Grid(ds_interp, coords={
        'X': {'center': 'xc', 'left': 'xg'},
        'Y': {'center': 'yc', 'left': 'yg'},
        'Z': {'center': 'zc'},
        'T': {'center': 'time'}
    })

    # print(U.shape, V.shape, T.shape, S.shape, Eta.shape)
    print(ds_interp)
    plot_mask(ds_interp, working_directory=config.get('working_directory', '.'))
    plot_bathy(ds_interp, working_directory=config.get('working_directory', '.'))
    plot_zbot(ds_interp, working_directory=config.get('working_directory', '.'))
    plot_surface_fields(ds_interp, grid, working_directory=config.get('working_directory', '.'))

if __name__ == "__main__":
    main()