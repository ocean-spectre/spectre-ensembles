#
#
# Notes:
#  We trim all arrays to exclude all boundary points from raw downloaded data
#

import numpy as np
import pandas as pd
import xarray as xr
import yaml
import os
from spectre_utils import common
import xgcm
import matplotlib.pyplot as plt

R = 6371229.0 # Radius of earth [m] (Consistent with NEMO)

def distance_m(dlon,dlat,lat):
    """ Calculates local distance in meters given a central latitude and dlon,dlat in degrees """

    dlon_ = np.deg2rad(dlon)
    dlat_ = np.deg2rad(dlat)
    lat_  = np.deg2rad(lat)
    return np.sqrt( R*R*( dlon_*dlon_*np.cos(lat_)*np.cos(lat_) + dlat_*dlat_ ) )

def lonlat_to_xyz(lon,lat):
    lon_ = np.deg2rad(lon)
    lat_ = np.deg2rad(lat)

    x = R*np.cos(lon_)*np.cos(lat_)
    y = R*np.sin(lon_)*np.cos(lat_)
    z = R*np.sin(lat_)

    return x, y, z

def main():
        
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)
    dataset_prefix = config.get('working_directory')
    npx = config.get("domain",{}).get("mpi",{}).get("npx",1)
    npy = config.get("domain",{}).get("mpi",{}).get("npy",1)
    i0 = config.get("domain",{}).get("longitude",{}).get("start",2)
    i1 = config.get("domain",{}).get("longitude",{}).get("end",-2)
    j0 = config.get("domain",{}).get("latitude",{}).get("start",2)
    j1 = config.get("domain",{}).get("latitude",{}).get("end",-2)

    ds = xr.open_dataset(f"{dataset_prefix}/glorysv12_mesh_hgr_glorys12_raw.static.nc")
    mask_ds = xr.open_dataset(f"{dataset_prefix}/glorysv12_mask_glorys12_raw.static.nc")
    zgr_ds = xr.open_dataset(f"{dataset_prefix}/glorysv12_mesh_zgr_glorys12_raw.static.nc")
    bathy_ds = xr.open_dataset(f"{dataset_prefix}/glorysv12_bathymetry_glorys12_raw.static.nc")

    bathy = -np.squeeze(bathy_ds['Bathymetry'].fillna(0).values)[j0:j1,i0:i1]
    zc = np.squeeze(zgr_ds['gdept_0'].values)
    zw = np.squeeze(zgr_ds['gdepw_0'].values)
    nz = zc.shape
    dz = np.zeros_like(zc)
    dz[:-1] = np.diff(zw) # Compute the cell heights.
    dz[-1] = 2.0*(zc[-1] - zw[-1]) 

    tmask = mask_ds['tmask'][0,0,j0:j1,i0:i1].squeeze()

    # Let's rename some variables in MITgcm lingo
    ds = ds.rename(
            {
                "glamt":"xC",
                "glamu":"xU",
                "glamv":"xV",
                "glamf":"xG",
                "gphit":"yC",
                "gphiu":"yU",
                "gphiv":"yV",
                "gphif":"yG"
            }
        )
    

    # Compute metric terms using analytical formula

    ## dxf
    #  dxf is the distance from the "west" to "east" edge center of a tracer cell
    #  Here "east" and "west" refer to the direction of increasing and decreasing "i"
    #  index, respectively.
    #  We use the analytical formula for distances and we need to know the change in 
    #  both longitude and latitude in the "i" direction, in addition to the central 
    #  latitude.
    #  NEMO output provides lat and lon at "U" points, which are the west and east
    #  edge centers of a tracer cell. The tracer cell centers are used for the 
    #  central latitude for dxf
    yc = ds['yC'].squeeze()
    xu = ds['xU'].squeeze()
    yu = ds['yU'].squeeze()
    dxu = xu[:,1:] - xu[:,:-1]
    dyu = yu[:,1:] - yu[:,:-1]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxu = np.concatenate([dxu, dxu[:,-1:]], axis=1)
    dyu = np.concatenate([dyu, dyu[:,-1:]], axis=1)
    dxF = distance_m( dxu, dyu, yc ) # Distance from "west" to "east" edge of tracer cell
    print(f" min/max dxu : {dxu.min()}, {dxu.max()}")
    print(f" min/max dyu : {dyu.min()}, {dyu.max()}")
    print(f" min/max dxF : {dxF.min()}, {dxF.max()}")

    ## dyf
    #  dyf is the distance from the "south" to "north" edge center of a tracer cell
    #  Here "south" and "north" refer to the direction of increasing and decreasing "j"
    #  index, respectively.
    #  We use the analytical formula for distances and we need to know the change in 
    #  both longitude and latitude in the "j" direction, in addition to the central 
    #  latitude.
    #  NEMO output provides lat and lon at "V" points, which are the south and north
    #  edge centers of a tracer cell. The tracer cell centers are used for the 
    #  central latitude for dxf
    xv = ds['xV'].squeeze()
    yv = ds['yV'].squeeze()
    dxv = xv[1:,:] - xv[:-1,:]
    dyv = yv[1:,:] - yv[:-1,:]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxv = np.concatenate([dxv, dxv[-1:,:]], axis=0)
    dyv = np.concatenate([dyv, dyv[-1:,:]], axis=0)
    dyF = distance_m( dxv, dyv, yc ) # Distance from "south" to "north" edge of tracer cell
    print(f" min/max dxv : {dxv.min()}, {dxv.max()}")
    print(f" min/max dyv : {dyv.min()}, {dyv.max()}")
    print(f" min/max dyF : {dyF.min()}, {dyF.max()}")

    ## dxg
    #  dxg is the distance from the "south-west" to "south-east" corner of a tracer cell
    #  Here "east" and "west" refer to the direction of increasing and decreasing "i"
    #  index, respectively.
    #  We use the analytical formula for distances and we need to know the change in 
    #  both longitude and latitude in the "i" direction, in addition to the central 
    #  latitude.
    #  NEMO output provides lat and lon at "U" points, which are the west and east
    #  edge centers of a tracer cell. The tracer cell centers are used for the 
    #  central latitude for dxf
    xg = ds['xG'].squeeze()
    yg = ds['yG'].squeeze()
    yc = 0.5*(yg[:,1:] + yg[:,:-1])
    dxg = xg[:,1:] - xg[:,:-1]
    dyg = yg[:,1:] - yg[:,:-1]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxg = np.concatenate([dxg, dxg[:,-1:]], axis=1)
    dyg = np.concatenate([dyg, dyg[:,-1:]], axis=1)
    yc = np.concatenate([yc, yc[:,-1:]], axis=1)
    dxG = distance_m( dxg, dyg, yc ) # Distance from "west" to "east" edge of tracer cell
    print(f" min/max dxg : {dxg.min()}, {dxg.max()}")
    print(f" min/max dyg : {dyg.min()}, {dyg.max()}")
    print(f" min/max dxG : {dxG.min()}, {dxG.max()}")

    ## dyg
    #  dyg is the distance from the "south-west" to "north-west" corner of a tracer cell
    #  Here "south" and "north" refer to the direction of increasing and decreasing "j"
    #  index, respectively.
    #  We use the analytical formula for distances and we need to know the change in 
    #  both longitude and latitude in the "j" direction, in addition to the central 
    #  latitude.
    #  NEMO output provides lat and lon at "V" points, which are the south and north
    #  edge centers of a tracer cell. The tracer cell centers are used for the 
    #  central latitude for dxf
    xg = ds['xG'].squeeze()
    yg = ds['yG'].squeeze()
    yc = 0.5*(yg[1:,:] + yg[:-1,:])
    dxg = xg[1:,:] - xg[:-1,:]
    dyg = yg[1:,:] - yg[:-1,:]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxg = np.concatenate([dxg, dxg[-1:,:]], axis=0)
    dyg = np.concatenate([dyg, dyg[-1:,:]], axis=0)
    yc = np.concatenate([yc, yc[-1:,:]], axis=0)
    dyG = distance_m( dxg, dyg, yc ) # Distance from "south" to "north" edge of tracer cell
    print(f" min/max dxg : {dxg.min()}, {dxg.max()}")
    print(f" min/max dyg : {dyg.min()}, {dyg.max()}")
    print(f" min/max dyG : {dyG.min()}, {dyG.max()}")

    ## dxc
    #  dxc is the distance from the cell centers of a tracer cell in the i direction
    #  We use the analytical formula for distances and we need to know the change in 
    #  both longitude and latitude in the "i" direction, in addition to the central 
    #  latitude.
    #  NEMO output provides lat and lon at "U" points, which are the west and east
    #  edge centers of a tracer cell. The tracer cell centers are used for the 
    #  central latitude for dxf
    xc = ds['xC'].squeeze()
    yc = ds['yC'].squeeze()
    yu = 0.5*(yc[:,1:] + yc[:,:-1])
    dxc = xc[:,1:] - xc[:,:-1]
    dyc = yc[:,1:] - yc[:,:-1]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxc = np.concatenate([dxc, dxc[:,-1:]], axis=1)
    dyc = np.concatenate([dyc, dyc[:,-1:]], axis=1)
    yu = np.concatenate([yu, yu[:,-1:]], axis=1)
    dxC = distance_m( dxc, dyc, yu ) # Distance from "west" to "east" edge of tracer cell
    print(f" min/max dxc : {dxc.min()}, {dxc.max()}")
    print(f" min/max dyc : {dyc.min()}, {dyc.max()}")
    print(f" min/max dxC : {dxC.min()}, {dxC.max()}")

    ## dyc
    #  dyc is the distance from the cell centers of a tracer cell in the j direction
    #  Here "south" and "north" refer to the direction of increasing and decreasing "j"
    #  index, respectively.
    #  We use the analytical formula for distances and we need to know the change in 
    #  both longitude and latitude in the "j" direction, in addition to the central 
    #  latitude.
    #  NEMO output provides lat and lon at "V" points, which are the south and north
    #  edge centers of a tracer cell. The tracer cell centers are used for the 
    #  central latitude for dxf
    xc = ds['xC'].squeeze()
    yc = ds['yC'].squeeze()
    yu = 0.5*(yc[1:,:] + yc[:-1,:])
    dxc = xc[1:,:] - xc[:-1,:]
    dyc = yc[1:,:] - yc[:-1,:]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxc = np.concatenate([dxc, dxc[-1:,:]], axis=0)
    dyc = np.concatenate([dyc, dyc[-1:,:]], axis=0)
    yu = np.concatenate([yu, yu[-1:,:]], axis=0)
    dyC = distance_m( dxc, dyc, yu ) # Distance from "south" to "north" edge of tracer cell
    print(f" min/max dxc : {dxc.min()}, {dxc.max()}")
    print(f" min/max dyc : {dyc.min()}, {dyc.max()}")
    print(f" min/max dyC : {dyC.min()}, {dyC.max()}")

    ## dxv
    xv = ds['xV'].squeeze()
    yv = ds['yV'].squeeze()
    yc = 0.5*(yv[:,1:] + yv[:,:-1])
    dxv = xv[:,1:] - xv[:,:-1]
    dyv = yv[:,1:] - yv[:,:-1]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxv = np.concatenate([dxv, dxv[:,-1:]], axis=1)
    dyv = np.concatenate([dyv, dyv[:,-1:]], axis=1)
    yc = np.concatenate([yc, yc[:,-1:]], axis=1)
    dxV = distance_m( dxv, dyv, yc ) # Distance from "west" to "east" edge of tracer cell
    print(f" min/max dxv : {dxv.min()}, {dxv.max()}")
    print(f" min/max dyv : {dyv.min()}, {dyv.max()}")
    print(f" min/max dxV : {dxV.min()}, {dxV.max()}")

    ## dyu
    xu = ds['xU'].squeeze()
    yu = ds['yU'].squeeze()
    yc = 0.5*(yu[1:,:] + yu[:-1,:])
    dxu = xu[1:,:] - xu[:-1,:]
    dyu = yu[1:,:] - yu[:-1,:]
    # Here, we prolong the last value of dxu and dyu in the first dimension
    dxu = np.concatenate([dxu, dxu[-1:,:]], axis=0)
    dyu = np.concatenate([dyu, dyu[-1:,:]], axis=0)
    yc = np.concatenate([yc, yc[-1:,:]], axis=0)
    dyU = distance_m( dxu, dyu, yc ) # Distance from "south" to "north" edge of tracer cell
    print(f" min/max dxu : {dxu.min()}, {dxu.max()}")
    print(f" min/max dyu : {dyu.min()}, {dyu.max()}")
    print(f" min/max dyU : {dyU.min()}, {dyU.max()}")

    ### Areas ###

    # Tracer cell area (rA)
    rA = np.zeros_like(np.squeeze(ds['xC'].values)) 
    rA[:-1,:-1] = 0.25*(dxG[:-1,:-1]*dyG[:-1,:-1] + # dxs*dxw
                        dxG[:-1,:-1]*dyG[:-1,1:]  + # dxs*dye
                        dxG[1:,:-1]*dyG[:-1,:-1]  + # dxn*dyw
                        dxG[1:,:-1]*dyG[:-1,1:])   # dxn*dye

    # Vorticity cell areas (rAz)
    rAz = np.zeros_like(np.squeeze(ds['xG'].values)) 
    rAz[1:,1:] = 0.25*(dxC[:-1,:-1]*dyC[:-1,:-1] + # dxs*dxw
                        dxC[:-1,:-1]*dyC[:-1,1:]  + # dxs*dye
                        dxC[1:,:-1]*dyC[:-1,:-1]  + # dxn*dyw
                        dxC[1:,:-1]*dyC[:-1,1:])   # dxn*dye

    # U-cell areas (raW)
    rAw = np.zeros_like(np.squeeze(ds['xU'].values)) 
    rAw[:-1,1:] = 0.25*(dxV[:-1,:-1]*dyF[:-1,:-1] + # dxs*dxw
                        dxV[:-1,:-1]*dyF[:-1,1:]  + # dxs*dye
                        dxV[1:,:-1]*dyF[:-1,:-1]  + # dxn*dyw
                        dxV[1:,:-1]*dyF[:-1,1:])   # dxn*dye

    # V-cell areas (raS)
    rAs = np.zeros_like(np.squeeze(ds['xV'].values))
    rAs[1:,:-1] = 0.25*(dxF[:-1,:-1]*dyU[:-1,:-1] + # dxs*dxw
                        dxF[:-1,:-1]*dyU[:-1,1:]  + # dxs*dye
                        dxF[1:,:-1]*dyU[:-1,:-1]  + # dxn*dyw
                        dxF[1:,:-1]*dyU[:-1,1:])   # dxn*dye

    ##################################
    # Write the horizgridfile
    ##################################

    be_dtype=np.dtype('>f8')
    xc = np.squeeze(ds['xC'].values.astype(be_dtype))[j0:j1,i0:i1]
    ny, nx = xc.shape
    print("===============================================")
    print("")
    print(f"Grid dimensions are nx * ny * nz : {nx} * {ny} * {nz}")
    print("")

    simulation_input_dir = os.path.join(config.get('simulation_directory', '.'), 'input')
    if not os.path.exists(simulation_input_dir):
        os.makedirs(simulation_input_dir)

    # for order of arrays, see https://lxr.mitgcm.org/lxr2/source/MITgcm/model/src/ini_curvilinear_grid.F#0278
    xc = np.squeeze(ds['xC'].values.astype(be_dtype))[j0:,i0:]
    yc = np.squeeze(ds['yC'].values.astype(be_dtype))[j0:,i0:]
    dxf = np.squeeze(dxF.astype(be_dtype))[j0:,i0:]
    dyf = np.squeeze(dyF.astype(be_dtype))[j0:,i0:]
    ra = np.squeeze(rA.astype(be_dtype))[j0:,i0:]
    xg = np.squeeze(ds['xG'].values.astype(be_dtype))[j0:,i0:]
    yg = np.squeeze(ds['yG'].values.astype(be_dtype))[j0:,i0:]
    dxv = np.squeeze(dxV.astype(be_dtype))[j0:,i0:]
    dyu = np.squeeze(dyU.astype(be_dtype))[j0:,i0:]
    raz = np.squeeze(rAz.astype(be_dtype))[j0:,i0:]
    dxc = np.squeeze(dxC.astype(be_dtype))[j0:,i0:]
    dyc = np.squeeze(dyC.astype(be_dtype))[j0:,i0:]
    raw = np.squeeze(rAw.astype(be_dtype))[j0:,i0:]
    ras = np.squeeze(rAs.astype(be_dtype))[j0:,i0:]
    dxg = np.squeeze(dxG.astype(be_dtype))[j0:,i0:]
    dyg = np.squeeze(dyG.astype(be_dtype))[j0:,i0:]
 
    nx_ = int(nx/npx)
    ny_ = int(ny/npy)
    for j in range(npy):
        for i in range(npx):
            horizgrid_arrays = np.concatenate(
                    [
                        xc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        yc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dxf[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dyf[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        ra[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        xg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1], 
                        yg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dxv[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dyu[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        raz[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dxc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dyc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        raw[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        ras[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dxg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                        dyg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1]
                    ]
                )

            faceid = i + j*npx+1
            with open(os.path.join(simulation_input_dir, f"tile{faceid:03d}.mitgrid"), 'wb') as f:
                f.write(horizgrid_arrays.astype(be_dtype).tobytes())

    # Write single horizgridfile for exch2 testing
    j=0
    i=0
    ny_=ny
    nx_=nx
    horizgrid_arrays = np.concatenate(
            [
                xc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                yc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dxf[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dyf[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                ra[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                xg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1], 
                yg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dxv[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dyu[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                raz[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dxc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dyc[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                raw[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                ras[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dxg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1],
                dyg[j*ny_:(j+1)*ny_+1,i*nx_:(i+1)*nx_+1]
            ]
        )

    with open(os.path.join(simulation_input_dir, f"horizgridfile.bin"), 'wb') as f:
        f.write(horizgrid_arrays.astype(be_dtype).tobytes())

    with open(os.path.join(simulation_input_dir, 'dz.bin'), 'wb') as f:
        dz.astype(np.dtype('>f4')).tofile(f)

    # Provide example flat bottomed bathymetry
    flat_bathymetry = np.zeros_like(xc)
    flat_bathymetry[1:,1:] = -3000.0  

    with open(os.path.join(simulation_input_dir, 'flat_bathymetry.bin'), 'wb') as f:
        flat_bathymetry.astype(np.dtype('>f4')).tofile(f)

    with open(os.path.join(simulation_input_dir, 'bathy.bin'), 'wb') as f:
        bathy.astype(np.dtype('>f4')).tofile(f)


#    ##################################
#    ### Plots ###
#    ##################################
#
#    
#    plt.pcolor(bathy)
#    plt.colorbar()
#    plt.title('bathy')
#    plt.savefig('bathy.png')
#    plt.close()
#
#    tmask.plot()
#    plt.title('Tmask')
#    plt.savefig('tmask.png')
#    plt.close()
#
#    ds['xC'].plot()
#    plt.title('xC')
#    plt.savefig('xc.png')
#    plt.close()
#
#    ds['yC'].plot()
#    plt.title('yC')
#    plt.savefig('yc.png')
#    plt.close()
#
#    ds['xU'].plot()
#    plt.title('xU')
#    plt.savefig('xu.png')
#    plt.close()
#
#    ds['yU'].plot()
#    plt.title('yU')
#    plt.savefig('yu.png')
#    plt.close()
#
#    ds['xV'].plot()
#    plt.title('xV')
#    plt.savefig('xv.png')
#    plt.close()
#
#    ds['yV'].plot()
#    plt.title('yV')
#    plt.savefig('yv.png')
#    plt.close()
#
#    plt.pcolor(dxF)
#    plt.colorbar()
#    plt.title('dxF')
#    plt.savefig('dxf.png')
#    plt.close()
#
#    plt.pcolor(dyF)
#    plt.colorbar()
#    plt.title('dyF')
#    plt.savefig('dyf.png')
#    plt.close()
#
#    plt.pcolor(dxG)
#    plt.colorbar()
#    plt.title('dxG')
#    plt.savefig('dxg.png')
#    plt.close()
#
#    plt.pcolor(dyG)
#    plt.colorbar()
#    plt.title('dyG')
#    plt.savefig('dyg.png')
#    plt.close()
#
#    plt.pcolor(dxC)
#    plt.colorbar()
#    plt.title('dxC')
#    plt.savefig('dxc.png')
#    plt.close()
#
#    plt.pcolor(dyC)
#    plt.colorbar()
#    plt.title('dyC')
#    plt.savefig('dyc.png')
#    plt.close()
#
#    plt.pcolor(dxV)
#    plt.colorbar()
#    plt.title('dxV')
#    plt.savefig('dxv.png')
#    plt.close()
#
#    plt.pcolor(dyU)
#    plt.colorbar()
#    plt.title('dyU')
#    plt.savefig('dyu.png')
#    plt.close()
#
#    plt.pcolor(rA)
#    plt.colorbar()
#    plt.title('Tracer cell areay (rA)')
#    plt.savefig('rA.png')
#    plt.close()
#
#    plt.pcolor(rAz)
#    plt.colorbar()
#    plt.title('Vorticity cell area (rAz)')
#    plt.savefig('rAz.png')
#    plt.close()
#
#    plt.pcolor(rAw)
#    plt.colorbar()
#    plt.title('U cell area (rAw)')
#    plt.savefig('rAw.png')
#    plt.close()
#
#    plt.pcolor(rAs)
#    plt.colorbar()
#    plt.title('V cell area (rAs)')
#    plt.savefig('rAs.png')
#    plt.close()
#
#    ds['e1t'].plot()
#    plt.savefig('e1t.png')
#    plt.close()
#
#    ds['e2t'].plot()
#    plt.savefig('e2t.png')
#    plt.close()


if __name__ == "__main__":
    main()
