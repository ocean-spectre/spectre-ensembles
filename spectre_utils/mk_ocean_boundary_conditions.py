import yaml
import os
import xarray as xr
from spectre_utils import common
import xgcm

# #def plot_boundary_cross_sections(ds, grid):
# #def plot_vertical_grid(ds, grid):
# def plot_surface_fields(ds, grid,working_directory='.'):
#     """Plot surface fields from the dataset."""
#     import matplotlib.pyplot as plt
#     import cartopy.crs as ccrs

#     fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
#     p = ds['Eta'].isel(time=0).plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
#     # show lat/lon grid
#     gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
#                         linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
#     gl.xlabels_top = False # Hide longitude labels at the top
#     gl.ylabels_right = False # Hide latitude labels on the right    plt.title('Sea Surface Height')
#     plt.savefig(os.path.join(working_directory, 'sea_surface_height.png'))

# def plot_mask(ds, working_directory='.'):
#     """Plot the mask from the dataset."""
#     import matplotlib.pyplot as plt
#     import cartopy.crs as ccrs

#     fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
#     p = ds['mask'][0,:,:].plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
#     # show lat/lon grid
#     gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
#                         linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
#     gl.xlabels_top = False # Hide longitude labels at the top
#     gl.ylabels_right = False # Hide latitude labels on the right

#     #ax.coastlines()
#     plt.title('Mask')
#     plt.savefig(os.path.join(working_directory, 'mask.png'))

# def plot_bathy(ds, working_directory='.'):
#     """Plot the bathymetry from the dataset."""
#     import matplotlib.pyplot as plt
#     import cartopy.crs as ccrs

#     fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
#     p = ds['bathy'].plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
#     # show lat/lon grid
#     gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
#                         linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
#     gl.xlabels_top = False # Hide longitude labels at the top
#     gl.ylabels_right = False # Hide latitude labels on the right

#     plt.title('Bathymetry')
#     plt.savefig(os.path.join(working_directory, 'bathymetry.png'))

# def plot_zbot(ds, working_directory='.'):
#     """Plot the zbot from the dataset."""
#     import matplotlib.pyplot as plt
#     import cartopy.crs as ccrs

#     fig, ax = plt.subplots(subplot_kw={'projection': ccrs.PlateCarree()})
#     p = ds['zbot'].plot(ax=ax, transform=ccrs.PlateCarree(), cmap='viridis', x='xc', y='yc')
#     # show lat/lon grid
#     gl = p.axes.gridlines(crs=ccrs.PlateCarree(), draw_labels=True,
#                         linewidth=0.5, color='gray', alpha=0.7, linestyle='--')
#     gl.xlabels_top = False # Hide longitude labels at the top
#     gl.ylabels_right = False # Hide latitude labels on the right

#     plt.title('Bottom cell layer')
#     plt.savefig(os.path.join(working_directory, 'zbot.png'))

# def plot_boundary_cross_sections(ds, grid, working_directory='.'):
#     """Plot boundary cross sections from the dataset."""
#     import matplotlib.pyplot as plt

#     def plot_cross_section(data,xlabel,title,filename):
#         fig, ax = plt.subplots(1,1, figsize=(10, 6))
#         pcm = data.plot(ax=ax, shading='auto', cmap='viridis')
#         plt.gca().invert_yaxis()
#         #plt.colorbar(pcm, label="mask")
#         plt.xlabel(xlabel)
#         plt.ylabel('Depth (m)')
#         plt.title(title)
#         plt.tight_layout()
#         plt.savefig(filename)

#     data = ds['mask']

#     # Define each boundary
#     north = data.sel(yc=ds.yc.max(), method='nearest')  # constant yc
#     south = data.sel(yc=ds.yc.min(), method='nearest')  # constant yc
#     east  = data.sel(xc=ds.xc.max(), method='nearest')  # constant xc
#     west  = data.sel(xc=ds.xc.min(), method='nearest')  # constant xc
#     plot_cross_section(north, 'Longitude', 'North Boundary Cross Section', os.path.join(working_directory, 'north_boundary_cross_section.png'))
#     plot_cross_section(south, 'Longitude', 'South Boundary Cross Section', os.path.join(working_directory, 'south_boundary_cross_section.png'))
#     plot_cross_section(east, 'Latitude', 'East Boundary Cross Section', os.path.join(working_directory, 'east_boundary_cross_section.png'))
#     plot_cross_section(west, 'Latitude', 'West Boundary Cross Section', os.path.join(working_directory, 'west_boundary_cross_section.png'))


def get_boundary_conditions(config):
    # Get time range from configuration
    time_range = config.get('domain').get('time')
    start_date = time_range.get('start')
    end_date = time_range.get('end')
    dataset_id = config.get('ocean').get('dataset_id')
    ocean_variables = config.get('ocean').get('variables')
    longitude_range = config.get('domain').get('longitude')
    min_long = longitude_range.get('min')
    max_long = longitude_range.get('max')
    dx = longitude_range.get('dx', 0.083333333)  # Default to 5 minutes if not specified
    latitude_range = config.get('domain').get('latitude')
    min_lat = latitude_range.get('min')
    max_lat = latitude_range.get('max')
    dy = latitude_range.get('dy', 0.083333333)  # Default to 5 minutes if not specified
    working_directory = config.get('working_directory', '.')
    dataset_prefix = config.get('ocean').get('prefix')
    min_depth = config.get('domain').get('depth', {}).get('min', 0)
    max_depth = config.get('domain').get('depth', {}).get('max', 6000)

    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    # Get the southern boundary conditions strip
    # We grabe the souther boundary plus one cell strip to the south
    # so that we can interpolate the meridional velocity onto the appropriate
    # C-grid location.
    ds_south, grid_south = common.from_copernicus(
        dataset_id=dataset_id,
        variables=ocean_variables,
        start_date=start_date,
        end_date=end_date,
        min_long=min_long,
        max_long=max_long,
        min_lat=min_lat,
        max_lat=min_lat+2.0*dy,
        min_depth=min_depth,
        max_depth=max_depth,
        working_directory=working_directory,
        dataset_prefix=f"{dataset_prefix}_south"
    )

    ds_north, grid_north = common.from_copernicus(
        dataset_id=dataset_id,
        variables=ocean_variables,
        start_date=start_date,
        end_date=end_date,
        min_long=min_long,
        max_long=max_long,
        min_lat=max_lat-2.0*dy,
        max_lat=max_lat,
        min_depth=min_depth,
        max_depth=max_depth,
        working_directory=working_directory,
        dataset_prefix=f"{dataset_prefix}_north"
    )

    ds_east, grid_east = common.from_copernicus(
        dataset_id=dataset_id,
        variables=ocean_variables,
        start_date=start_date,
        end_date=end_date,
        min_long=max_long-2.0*dx,
        max_long=max_long,
        min_lat=min_lat,
        max_lat=max_lat,
        min_depth=min_depth,
        max_depth=max_depth,
        working_directory=working_directory,
        dataset_prefix=f"{dataset_prefix}_east"
    )

    ds_west, grid_west = common.from_copernicus(
        dataset_id=dataset_id,
        variables=ocean_variables,
        start_date=start_date,
        end_date=end_date,
        min_long=min_long,
        max_long=min_long+2.0*dx,
        min_lat=min_lat,
        max_lat=max_lat,
        min_depth=min_depth,
        max_depth=max_depth,
        working_directory=working_directory,
        dataset_prefix=f"{dataset_prefix}_west"
    )


    return {"east": (ds_east, grid_east),
            "west": (ds_west, grid_west),
            "north": (ds_north, grid_north),
            "south": (ds_south, grid_south)}

def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)
    
    bcs = get_boundary_conditions(config)
    
    simulation_input_dir = os.path.join(config.get('simulation_directory', '.'), 'input')
    if not os.path.exists(simulation_input_dir):
        os.makedirs(simulation_input_dir)

    ###############################################################################
    # South boundary conditions
    ###############################################################################
    ds, grid = bcs['south']
    print("Processing South boundary conditions...")
    print("=========================================================")

    if ds.isnull().any():
        print("Warning: Input dataset contains NaN values. Patching values...")
        #Check if mask is identical to the locations where nan's are found
        ds['uo'] = ds['uo'].fillna(0)
        ds['vo'] = ds['vo'].fillna(0)
        ds['thetao'] = ds['thetao'].fillna(0)
        ds['so'] = ds['so'].fillna(0)
        ds['zos'] = ds['zos'].fillna(0)
        print(ds.isnull().sum())

    # Now, we need to interpolate to the c-grid locations
    U = grid.interp(ds['uo'],axis='X')[...,1,1:-1]
    V = grid.interp(ds['vo'],axis='Y')[...,1,1:-1]
    T = ds['thetao'][...,1,1:-1]
    S = ds['so'][...,1,1:-1]
    Eta = ds['zos'][...,1,1:-1]

    print(f"min(XG) : {ds['xg'][1:-1].min().values}, max(XG) : {ds['xg'][1:-1].max().values}")
    print(f"min(XC) : {ds['xc'][1:-1].min().values}, max(XC) : {ds['xc'][1:-1].max().values}")
    print(f"min(YG) : {ds['yg'][1:-1].min().values}, max(YG) : {ds['yg'][1:-1].max().values}")
    print(f"min(YC) : {ds['yc'][1:-1].min().values}, max(YC) : {ds['yc'][1:-1].max().values}")

    print(f"U shape: {U.shape}, V shape: {V.shape}, T shape: {T.shape}, S shape: {S.shape}, Eta shape: {Eta.shape}")
    # create new dataset with interpolated variables
    ds_interp = xr.Dataset({
        'U': (['time', 'zc', 'xg'], U.values),
        'V': (['time', 'zc', 'xc'], V.values),
        'T': (['time', 'zc', 'xc'], T.values),
        'S': (['time', 'zc', 'xc'], S.values),
        'Eta': (['time', 'xc'], Eta.values),
    }, coords={
        'time': ds['time'],
        'zc': ds['zc'],
        'xc': ds['xc'][1:-1],
        'xg': ds['xg'][1:-1],
    })
    grid_interp = xgcm.Grid(ds_interp, coords={
        'X': {'center': 'xc', 'left': 'xg'},
        'Z': {'center': 'zc'},
        'T': {'center': 'time'}
    })


    with open(os.path.join(simulation_input_dir, 'U.south.bin'), 'wb') as f:
        ds_interp['U'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'V.south.bin'), 'wb') as f:
        ds_interp['V'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'T.south.bin'), 'wb') as f:
        ds_interp['T'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'S.south.bin'), 'wb') as f:
        ds_interp['S'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'Eta.south.bin'), 'wb') as f:
        ds_interp['Eta'].values.astype('>f4').tofile(f)
    print("=========================================================")

    ###############################################################################
    # North boundary conditions
    ###############################################################################
    ds, grid = bcs['north']
    print("Processing North boundary conditions...")
    print("=========================================================")
    if ds.isnull().any():
        print("Warning: Input dataset contains NaN values. Patching values...")
        #Check if mask is identical to the locations where nan's are found
        ds['uo'] = ds['uo'].fillna(0)
        ds['vo'] = ds['vo'].fillna(0)
        ds['thetao'] = ds['thetao'].fillna(0)
        ds['so'] = ds['so'].fillna(0)
        ds['zos'] = ds['zos'].fillna(0)
        print(ds.isnull().sum())

    # Now, we need to interpolate to the c-grid locations
    U = grid.interp(ds['uo'],axis='X')[...,-1,1:-1]
    V = grid.interp(ds['vo'],axis='Y')[...,-1,1:-1]
    T = ds['thetao'][...,-1,1:-1]
    S = ds['so'][...,-1,1:-1]
    Eta = ds['zos'][...,-1,1:-1]

    print(f"min(XG) : {ds['xg'][1:-1].min().values}, max(XG) : {ds['xg'][1:-1].max().values}")
    print(f"min(XC) : {ds['xc'][1:-1].min().values}, max(XC) : {ds['xc'][1:-1].max().values}")
    print(f"min(YG) : {ds['yg'][1:-1].min().values}, max(YG) : {ds['yg'][1:-1].max().values}")
    print(f"min(YC) : {ds['yc'][1:-1].min().values}, max(YC) : {ds['yc'][1:-1].max().values}")

    print(f"U shape: {U.shape}, V shape: {V.shape}, T shape: {T.shape}, S shape: {S.shape}, Eta shape: {Eta.shape}")
    # create new dataset with interpolated variables
    ds_interp = xr.Dataset({
        'U': (['time', 'zc', 'xg'], U.values),
        'V': (['time', 'zc', 'xc'], V.values),
        'T': (['time', 'zc', 'xc'], T.values),
        'S': (['time', 'zc', 'xc'], S.values),
        'Eta': (['time', 'xc'], Eta.values),
    }, coords={
        'time': ds['time'],
        'zc': ds['zc'],
        'xc': ds['xc'][1:-1],
        'xg': ds['xg'][1:-1],
    })
    grid_interp = xgcm.Grid(ds_interp, coords={
        'X': {'center': 'xc', 'left': 'xg'},
        'Z': {'center': 'zc'},
        'T': {'center': 'time'}
    })

    with open(os.path.join(simulation_input_dir, 'U.north.bin'), 'wb') as f:
        ds_interp['U'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'V.north.bin'), 'wb') as f:
        ds_interp['V'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'T.north.bin'), 'wb') as f:
        ds_interp['T'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'S.north.bin'), 'wb') as f:
        ds_interp['S'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'Eta.north.bin'), 'wb') as f:
        ds_interp['Eta'].values.astype('>f4').tofile(f)

    print("=========================================================")

    ###############################################################################
    # West boundary conditions
    ###############################################################################
    ds, grid = bcs['west']
    print("Processing West boundary conditions...")
    print("=========================================================")
    if ds.isnull().any():
        print("Warning: Input dataset contains NaN values. Patching values...")
        #Check if mask is identical to the locations where nan's are found
        ds['uo'] = ds['uo'].fillna(0)
        ds['vo'] = ds['vo'].fillna(0)
        ds['thetao'] = ds['thetao'].fillna(0)
        ds['so'] = ds['so'].fillna(0)
        ds['zos'] = ds['zos'].fillna(0)
        print(ds.isnull().sum())

    # Now, we need to interpolate to the c-grid locations
    U = grid.interp(ds['uo'],axis='X')[...,1:-1,1]
    V = grid.interp(ds['vo'],axis='Y')[...,1:-1,1]
    T = ds['thetao'][...,1:-1,1]
    S = ds['so'][...,1:-1,1]
    Eta = ds['zos'][...,1:-1,1]

    print(f"min(XG) : {ds['xg'][1:-1].min().values}, max(XG) : {ds['xg'][1:-1].max().values}")
    print(f"min(XC) : {ds['xc'][1:-1].min().values}, max(XC) : {ds['xc'][1:-1].max().values}")
    print(f"min(YG) : {ds['yg'][1:-1].min().values}, max(YG) : {ds['yg'][1:-1].max().values}")
    print(f"min(YC) : {ds['yc'][1:-1].min().values}, max(YC) : {ds['yc'][1:-1].max().values}")

    print(f"U shape: {U.shape}, V shape: {V.shape}, T shape: {T.shape}, S shape: {S.shape}, Eta shape: {Eta.shape}")
    # create new dataset with interpolated variables
    ds_interp = xr.Dataset({
        'U': (['time', 'zc', 'yc'], U.values),
        'V': (['time', 'zc', 'yg'], V.values),
        'T': (['time', 'zc', 'yc'], T.values),
        'S': (['time', 'zc', 'yc'], S.values),
        'Eta': (['time', 'xc'], Eta.values),
    }, coords={
        'time': ds['time'],
        'zc': ds['zc'],
        'yc': ds['yc'][1:-1],
        'yg': ds['yg'][1:-1],
    })
    grid_interp = xgcm.Grid(ds_interp, coords={
        'Y': {'center': 'yc', 'left': 'yg'},
        'Z': {'center': 'zc'},
        'T': {'center': 'time'}
    })

    with open(os.path.join(simulation_input_dir, 'U.west.bin'), 'wb') as f:
        ds_interp['U'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'V.west.bin'), 'wb') as f:
        ds_interp['V'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'T.west.bin'), 'wb') as f:
        ds_interp['T'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'S.west.bin'), 'wb') as f:
        ds_interp['S'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'Eta.west.bin'), 'wb') as f:
        ds_interp['Eta'].values.astype('>f4').tofile(f)

    print("=========================================================")

        ###############################################################################
    # West boundary conditions
    ###############################################################################
    ds, grid = bcs['west']
    print("Processing West boundary conditions...")
    print("=========================================================")
    if ds.isnull().any():
        print("Warning: Input dataset contains NaN values. Patching values...")
        #Check if mask is identical to the locations where nan's are found
        ds['uo'] = ds['uo'].fillna(0)
        ds['vo'] = ds['vo'].fillna(0)
        ds['thetao'] = ds['thetao'].fillna(0)
        ds['so'] = ds['so'].fillna(0)
        ds['zos'] = ds['zos'].fillna(0)
        print(ds.isnull().sum())

    # Now, we need to interpolate to the c-grid locations
    U = grid.interp(ds['uo'],axis='X')[...,1:-1,-1]
    V = grid.interp(ds['vo'],axis='Y')[...,1:-1,-1]
    T = ds['thetao'][...,1:-1,-1]
    S = ds['so'][...,1:-1,-1]
    Eta = ds['zos'][...,1:-1,-1]

    print(f"min(XG) : {ds['xg'][1:-1].min().values}, max(XG) : {ds['xg'][1:-1].max().values}")
    print(f"min(XC) : {ds['xc'][1:-1].min().values}, max(XC) : {ds['xc'][1:-1].max().values}")
    print(f"min(YG) : {ds['yg'][1:-1].min().values}, max(YG) : {ds['yg'][1:-1].max().values}")
    print(f"min(YC) : {ds['yc'][1:-1].min().values}, max(YC) : {ds['yc'][1:-1].max().values}")

    print(f"U shape: {U.shape}, V shape: {V.shape}, T shape: {T.shape}, S shape: {S.shape}, Eta shape: {Eta.shape}")
    # create new dataset with interpolated variables
    ds_interp = xr.Dataset({
        'U': (['time', 'zc', 'yc'], U.values),
        'V': (['time', 'zc', 'yg'], V.values),
        'T': (['time', 'zc', 'yc'], T.values),
        'S': (['time', 'zc', 'yc'], S.values),
        'Eta': (['time', 'yc'], Eta.values),
    }, coords={
        'time': ds['time'],
        'zc': ds['zc'],
        'yc': ds['yc'][1:-1],
        'yg': ds['yg'][1:-1],
    })
    grid_interp = xgcm.Grid(ds_interp, coords={
        'Y': {'center': 'yc', 'left': 'yg'},
        'Z': {'center': 'zc'},
        'T': {'center': 'time'}
    })

    with open(os.path.join(simulation_input_dir, 'U.east.bin'), 'wb') as f:
        ds_interp['U'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'V.east.bin'), 'wb') as f:
        ds_interp['V'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'T.east.bin'), 'wb') as f:
        ds_interp['T'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'S.east.bin'), 'wb') as f:
        ds_interp['S'].values.astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'Eta.east.bin'), 'wb') as f:
        ds_interp['Eta'].values.astype('>f4').tofile(f)

    print("=========================================================")


if __name__ == "__main__":
    main()
