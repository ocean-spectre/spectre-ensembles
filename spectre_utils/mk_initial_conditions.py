import yaml
import os
import xarray as xr
import numpy as np
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

def plot_where_nan(ds, working_directory='.'):
    """Plot the mask from the dataset."""
    import matplotlib.pyplot as plt
    import cartopy.crs as ccrs

    fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
    # Create a mask where the data is NaN as integers
    nan_mask = ds['zos'].fillna(-1000)
    p = nan_mask[0,:,:].plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
    # show lat/lon grid
    gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
                        linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
    gl.xlabels_top = False # Hide longitude labels at the top
    gl.ylabels_right = False # Hide latitude labels on the right

    #ax.coastlines()
    plt.title('Mask')
    plt.savefig(os.path.join(working_directory, 'nan_mask_T.png'))

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

def plot_boundary_cross_sections(ds, grid, working_directory='.'):
    """Plot boundary cross sections from the dataset."""
    import matplotlib.pyplot as plt

    def plot_cross_section(data,xlabel,title,filename):
        fig, ax = plt.subplots(1,1, figsize=(10, 6))
        pcm = data.plot(ax=ax, shading='auto', cmap='viridis')
        plt.gca().invert_yaxis()
        #plt.colorbar(pcm, label="mask")
        plt.xlabel(xlabel)
        plt.ylabel('Depth (m)')
        plt.title(title)
        plt.tight_layout()
        plt.savefig(filename)

    data = ds['mask']

    # Define each boundary
    north = data.sel(yc=ds.yc.max(), method='nearest')  # constant yc
    south = data.sel(yc=ds.yc.min(), method='nearest')  # constant yc
    east  = data.sel(xc=ds.xc.max(), method='nearest')  # constant xc
    west  = data.sel(xc=ds.xc.min(), method='nearest')  # constant xc
    plot_cross_section(north, 'Longitude', 'North Boundary Cross Section', os.path.join(working_directory, 'north_boundary_cross_section.png'))
    plot_cross_section(south, 'Longitude', 'South Boundary Cross Section', os.path.join(working_directory, 'south_boundary_cross_section.png'))
    plot_cross_section(east, 'Latitude', 'East Boundary Cross Section', os.path.join(working_directory, 'east_boundary_cross_section.png'))
    plot_cross_section(west, 'Latitude', 'West Boundary Cross Section', os.path.join(working_directory, 'west_boundary_cross_section.png'))


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

    if ds.isnull().any():
        print("Warning: Input dataset contains NaN values. Patching values...")
        #Check if mask is identical to the locations where nan's are found
        ds['uo'] = ds['uo'].fillna(0)
        ds['vo'] = ds['vo'].fillna(0)
        ds['thetao'] = ds['thetao'].fillna(0)
        ds['so'] = ds['so'].fillna(0)
        ds['zos'] = ds['zos'].fillna(0)
        print(ds.isnull().sum())

    if ds_static.isnull().any():
        print("Warning: Input statics dataset contains NaN values. Patching values...")
        #Check if mask is identical to the locations where nan's are found
        ds_static['deptho'] = ds_static['deptho'].fillna(0)
        ds_static['deptho_lev' ] = ds_static['deptho_lev'].fillna(0)
        print(ds_static.isnull().sum())

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

    print(ds_interp)
    # Check if there are any NaN values in the dataset
    if ds_interp.isnull().any():
        print("Warning: The dataset contains NaN values. This may cause issues in the simulation.")
        print(ds_interp.isnull().sum())

    plot_mask(ds_interp, working_directory=config.get('working_directory', '.'))
    plot_bathy(ds_interp, working_directory=config.get('working_directory', '.'))
    plot_zbot(ds_interp, working_directory=config.get('working_directory', '.'))
    plot_surface_fields(ds_interp, grid_interp, working_directory=config.get('working_directory', '.'))
    plot_boundary_cross_sections(ds_interp, grid_interp, working_directory=config.get('working_directory', '.'))

    # Write each component to a big-endian single precision binary file
    simulation_input_dir = os.path.join(config.get('simulation_directory', '.'), 'input')
    if not os.path.exists(simulation_input_dir):
        os.makedirs(simulation_input_dir)
    with open(os.path.join(simulation_input_dir, 'U.init.bin'), 'wb') as f:
        ds_interp['U'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'V.init.bin'), 'wb') as f:
        ds_interp['V'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'T.init.bin'), 'wb') as f:
        ds_interp['T'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'S.init.bin'), 'wb') as f:
        ds_interp['S'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'Eta.init.bin'), 'wb') as f:
        ds_interp['Eta'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'mask.bin'), 'wb') as f:
        ds_interp['mask'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'zbot.bin'), 'wb') as f:
        ds_interp['zbot'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'bathy.bin'), 'wb') as f:
        ds_interp['bathy'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'xc.bin'), 'wb') as f:
        ds_interp['xc'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'yc.bin'), 'wb') as f:
        ds_interp['yc'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'zc.bin'), 'wb') as f:
        ds_interp['zc'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'xg.bin'), 'wb') as f:
        ds_interp['xg'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'yg.bin'), 'wb') as f:
        ds_interp['yg'].values.astype('>f4').tofile(f)



if __name__ == "__main__":
    main()