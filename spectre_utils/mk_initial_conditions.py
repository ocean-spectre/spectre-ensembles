import yaml
import os
import xarray as xr
import numpy as np
from spectre_utils import common
import xgcm


def get_initial_conditions(working_directory):

    S = xr.open_dataset(f"{working_directory}/glorysv12_S_glorys12_raw.0.nc")['vosaline']
    T = xr.open_dataset(f"{working_directory}/glorysv12_T_glorys12_raw.0.nc")['votemper']
    U = xr.open_dataset(f"{working_directory}/glorysv12_U_glorys12_raw.0.nc")['vozocrtx']
    V = xr.open_dataset(f"{working_directory}/glorysv12_V_glorys12_raw.0.nc")['vomecrty']
    Eta = xr.open_dataset(f"{working_directory}/glorysv12_grid2D_glorys12_raw.0.nc")['sossheig']



    return U, V, T, S, Eta


def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    working_directory = config.get('working_directory')
    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    npx = config.get("domain",{}).get("mpi",{}).get("npx",1)
    npy = config.get("domain",{}).get("mpi",{}).get("npy",1)
    i0 = config.get("domain",{}).get("longitude",{}).get("start",2)
    i1 = config.get("domain",{}).get("longitude",{}).get("end",-2)
    j0 = config.get("domain",{}).get("latitude",{}).get("start",2)
    j1 = config.get("domain",{}).get("latitude",{}).get("end",-2)
    
    U, V, T, S, Eta = get_initial_conditions(working_directory)

    # Create a derived bathymetry input from the temperature field nanmask
    # For some reason, this bathymetry is distinct from the bathymetry data 
    # provided with the Glorys/NEMO netcdf files
    zgr_ds = xr.open_dataset(f"{working_directory}/glorysv12_mesh_zgr_glorys12_raw.static.nc")
    zc = np.squeeze(zgr_ds['gdept_0'].values)
    zw = np.squeeze(zgr_ds['gdepw_0'].values)
    nz = zc.shape
    dz = np.zeros_like(zc)
    dz[:-1] = np.diff(zw) # Compute the cell heights.
    dz[-1] = 2.0*(zc[-1] - zw[-1]) 
    t_domain = np.squeeze(T.values[0,:,j0:j1,i0:i1])
    nz, ny, nx = t_domain.shape
    wetmask = ~np.isnan(t_domain)
    dz_domain = np.broadcast_to(dz[:,None,None], (len(dz),ny,nx))
    derived_bathy = -np.squeeze(np.sum(dz_domain*wetmask, axis=0))

    # Fill nan's to zero
    U = U.fillna(0)
    V = V.fillna(0)
    T = T.fillna(0)
    S = S.fillna(0)
    Eta = Eta.fillna(0)

    # Verify that [j0,i0] for each variable corresponds to the same cell
    # Write lower left corner x,y for Temperature
    print(" ====== U coords ====== ")
    print(U.coords)
    print(" --> Longitude <-- ")
    print(U.coords['nav_lon'][j0,i0-1].values)
    print(U.coords['nav_lon'][j0,i0].values)
    print(U.coords['nav_lon'][j0,i0+1].values)
    print(" --> Latitude <-- ")
    print(U.coords['nav_lat'][j0,i0].values)
    print(" ====== V coords ====== ")
    print(V.coords)
    print(" --> Longitude <-- ")
    print(V.coords['nav_lon'][j0,i0].values)
    print(" --> Latitude <-- ")
    print(V.coords['nav_lat'][j0-1,i0].values)
    print(V.coords['nav_lat'][j0,i0].values)
    print(V.coords['nav_lat'][j0+1,i0].values)
    print(" ====== T coords ====== ")
    print(T.coords)
    print(" --> Longitude <-- ")
    print(T.coords['nav_lon'][j0,i0].values)
    print(" --> Latitude <-- ")
    print(T.coords['nav_lat'][j0,i0].values)
    print(" ====== S coords ====== ")
    print(S.coords)
    print(" --> Longitude <-- ")
    print(S.coords['nav_lon'][j0,i0].values)
    print(" --> Latitude <-- ")
    print(S.coords['nav_lat'][j0,i0].values)
    print(" ====== Eta coords ====== ")
    print(Eta.coords)
    print(" --> Longitude <-- ")
    print(Eta.coords['nav_lon'][j0,i0].values)
    print(" --> Latitude <-- ")
    print(Eta.coords['nav_lat'][j0,i0].values)

    # Write each component to a big-endian single precision binary file
    simulation_input_dir = os.path.join(config.get('simulation_directory', '.'), 'input')
    if not os.path.exists(simulation_input_dir):
        os.makedirs(simulation_input_dir)

    with open(os.path.join(simulation_input_dir, 'derived_bathy.bin'), 'wb') as f:
        derived_bathy.astype('>f4').tofile(f)
        print(f"U shape: {U.values[0,:,j0:j1,i0:i1-1].shape}")
    with open(os.path.join(simulation_input_dir, 'U.init.bin'), 'wb') as f:
        U.values[0,:,j0:j1,i0:i1-1].astype('>f4').tofile(f)
        print(f"U shape: {U.values[0,:,j0:j1,i0:i1-1].shape}")
    with open(os.path.join(simulation_input_dir, 'V.init.bin'), 'wb') as f:
        V.values[0,:,j0:j1,i0:i1].astype('>f4').tofile(f)
        print(f"V shape: {V.values[0,:,j0:j1,i0:i1].shape}")
    with open(os.path.join(simulation_input_dir, 'T.init.bin'), 'wb') as f:
        T.values[0,:,j0:j1,i0:i1].astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'S.init.bin'), 'wb') as f:
        S.values[0,:,j0:j1,i0:i1].astype('>f4').tofile(f)
    with open(os.path.join(simulation_input_dir, 'Eta.init.bin'), 'wb') as f:
        Eta.values[0,j0:j1,i0:i1].astype('>f4').tofile(f)


if __name__ == "__main__":
    main()
