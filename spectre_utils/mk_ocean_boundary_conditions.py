import yaml
import os
import xarray as xr
import numpy as np
from spectre_utils import common
import xgcm


def get_ocean_state(working_directory):

    # TO DO : when we have multiple nc files per var, we'll need to use open_mfdataset
    S = xr.open_mfdataset(f"{working_directory}/glorysv12_S_glorys12_raw.*.nc")['vosaline']
    T = xr.open_mfdataset(f"{working_directory}/glorysv12_T_glorys12_raw.*.nc")['votemper']
    U = xr.open_mfdataset(f"{working_directory}/glorysv12_U_glorys12_raw.*.nc")['vozocrtx']
    V = xr.open_mfdataset(f"{working_directory}/glorysv12_V_glorys12_raw.*.nc")['vomecrty']
    Eta = xr.open_mfdataset(f"{working_directory}/glorysv12_grid2D_glorys12_raw.*.nc")['sossheig']

    U = U.fillna(0)
    V = V.fillna(0)
    T = T.fillna(0)
    S = S.fillna(0)
    Eta = Eta.fillna(0)

    return U, V, T, S, Eta


def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    working_directory = config.get('working_directory')
    if not os.path.exists(working_directory):
        os.makedirs(working_directory)

    simulation_input_dir = os.path.join(config.get('simulation_directory', '.'), 'input')
    if not os.path.exists(simulation_input_dir):
        os.makedirs(simulation_input_dir)


    i0 = config.get("domain",{}).get("longitude",{}).get("start",2)
    i1 = config.get("domain",{}).get("longitude",{}).get("end",-2)
    j0 = config.get("domain",{}).get("latitude",{}).get("start",2)
    j1 = config.get("domain",{}).get("latitude",{}).get("end",-2)
    
    U, V, T, S, Eta = get_ocean_state(working_directory)
    print(U.coords)

    # Write each component to a big-endian single precision binary file

    # South
    print("========================================")
    print(" Writing south boundary conditions ")
    print("")
    u = U.isel(y=j0,x=slice(i0,i1-1),drop=True)
    v = V.isel(y=j0,x=slice(i0,i1),drop=True)
    t = T.isel(y=j0,x=slice(i0,i1),drop=True)
    s = S.isel(y=j0,x=slice(i0,i1),drop=True)
    eta = Eta.isel(y=j0,x=slice(i0,i1),drop=True)

    with open(os.path.join(simulation_input_dir, 'U.south.bin'), 'wb') as f:
        (u.values).astype('>f4').tofile(f)
    print(f"U_south shape: {u.shape}")
    with open(os.path.join(simulation_input_dir, 'V.south.bin'), 'wb') as f:
        (v.values).astype('>f4').tofile(f)
    print(f"V_south shape: {v.shape}")
    with open(os.path.join(simulation_input_dir, 'T.south.bin'), 'wb') as f:
        (t.values).astype('>f4').tofile(f)
    print(f"T_south shape: {t.shape}")
    with open(os.path.join(simulation_input_dir, 'S.south.bin'), 'wb') as f:
        (s.values).astype('>f4').tofile(f)
    print(f"S_south shape: {s.shape}")
    with open(os.path.join(simulation_input_dir, 'Eta.south.bin'), 'wb') as f:
        (eta.values).astype('>f4').tofile(f)
    print(f"Eta_south shape: {eta.shape}")

    # North
    print("========================================")
    print(" Writing north boundary conditions ")
    print("")
    u = U.isel(y=j1,x=slice(i0,i1-1),drop=True)
    v = V.isel(y=j1,x=slice(i0,i1),drop=True)
    t = T.isel(y=j1,x=slice(i0,i1),drop=True)
    s = S.isel(y=j1,x=slice(i0,i1),drop=True)
    eta = Eta.isel(y=j1,x=slice(i0,i1),drop=True)

    with open(os.path.join(simulation_input_dir, 'U.north.bin'), 'wb') as f:
        (u.values).astype('>f4').tofile(f)
        print(f"U_north shape: {u.shape}")
    with open(os.path.join(simulation_input_dir, 'V.north.bin'), 'wb') as f:
        (v.values).astype('>f4').tofile(f)
        print(f"V_north shape: {v.shape}")
    with open(os.path.join(simulation_input_dir, 'T.north.bin'), 'wb') as f:
        (t.values).astype('>f4').tofile(f)
        print(f"T_north shape: {t.shape}")
    with open(os.path.join(simulation_input_dir, 'S.north.bin'), 'wb') as f:
        (s.values).astype('>f4').tofile(f)
        print(f"S_north shape: {s.shape}")
    with open(os.path.join(simulation_input_dir, 'Eta.north.bin'), 'wb') as f:
        (eta.values).astype('>f4').tofile(f)
        print(f"Eta_north shape: {eta.shape}")

    # West
    print("========================================")
    print(" Writing west boundary conditions ")
    print("")
    u   = U.isel(y=slice(j0,j1),x=i0,drop=True)
    v   = V.isel(y=slice(j0,j1),x=i0,drop=True)
    t   = T.isel(y=slice(j0,j1),x=i0,drop=True)
    s   = S.isel(y=slice(j0,j1),x=i0,drop=True)
    eta = Eta.isel(y=slice(j0,j1),x=i0,drop=True)

    with open(os.path.join(simulation_input_dir, 'U.west.bin'), 'wb') as f:
        (u.values).astype('>f4').tofile(f)
        print(f"U_west shape: {u.shape}")
    with open(os.path.join(simulation_input_dir, 'V.west.bin'), 'wb') as f:
        (v.values).astype('>f4').tofile(f)
        print(f"V_west shape: {v.shape}")
    with open(os.path.join(simulation_input_dir, 'T.west.bin'), 'wb') as f:
        (t.values).astype('>f4').tofile(f)
        print(f"T_west shape: {t.shape}")
    with open(os.path.join(simulation_input_dir, 'S.west.bin'), 'wb') as f:
        (s.values).astype('>f4').tofile(f)
        print(f"S_west shape: {s.shape}")
    with open(os.path.join(simulation_input_dir, 'Eta.west.bin'), 'wb') as f:
        (eta.values).astype('>f4').tofile(f)

    # East
    print("========================================")
    print(" Writing east boundary conditions ")
    print("")
    u   = U.isel(y=slice(j0,j1),x=i1,drop=True)
    v   = V.isel(y=slice(j0,j1),x=i1,drop=True)
    t   = T.isel(y=slice(j0,j1),x=i1,drop=True)
    s   = S.isel(y=slice(j0,j1),x=i1,drop=True)
    eta = Eta.isel(y=slice(j0,j1),x=i1,drop=True)

    with open(os.path.join(simulation_input_dir, 'U.east.bin'), 'wb') as f:
        (u.values).astype('>f4').tofile(f)
        print(f"U_east shape: {u.shape}")
    with open(os.path.join(simulation_input_dir, 'V.east.bin'), 'wb') as f:
        (v.values).astype('>f4').tofile(f)
        print(f"V_east shape: {v.shape}")
    with open(os.path.join(simulation_input_dir, 'T.east.bin'), 'wb') as f:
        (t.values).astype('>f4').tofile(f)
        print(f"T_east shape: {t.shape}")
    with open(os.path.join(simulation_input_dir, 'S.east.bin'), 'wb') as f:
        (s.values).astype('>f4').tofile(f)
        print(f"S_east shape: {s.shape}")
    with open(os.path.join(simulation_input_dir, 'Eta.east.bin'), 'wb') as f:
        (eta.values).astype('>f4').tofile(f)
      
if __name__ == "__main__":
    main()
