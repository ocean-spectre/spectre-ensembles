import cdsapi
import os
from spectre_utils import common
import yaml
import numpy as np
import sys
import xarray as xr
from metpy.calc import specific_humidity_from_dewpoint
from metpy.units import units
from datetime import datetime, timedelta
import pandas as pd

def main():

    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    working_directory = config['working_directory']
    simulation_directory = config['simulation_directory']
    years= config['atmosphere']['years']
    vars= config['atmosphere']['variables']
    prefix = config['atmosphere']['prefix']

    # Load in the xc,yc grid from the simulation directory
    simulation_input_dir = os.path.join(simulation_directory, 'input')
    with open(os.path.join(simulation_input_dir, 'xc.bin'), 'rb') as f:
        xc = np.fromfile(f, dtype='>f4')
    with open(os.path.join(simulation_input_dir, 'yc.bin'), 'rb') as f:
        yc = np.fromfile(f, dtype='>f4')

    t1 = datetime.strptime(config['domain']['time']['start'], "%Y-%m-%d")
    t2 = datetime.strptime(config['domain']['time']['end'], "%Y-%m-%d")


    # Time range
    # Load in the netcdf files for the era5 datafor var in vars.keys():
    era5_files = []
    for var in vars.keys():
        for year in years:
            target = f"{working_directory}/{prefix}_{vars[var]}_{year}.nc"
            if not os.path.exists(target):
                print(f"File {target} does not exist, go back and run download_era5.py")
                sys.exit(1)
            era5_files.append(target)

    # Load a multi-file dataset from the era5 files
    ds = xr.open_mfdataset(era5_files, combine='by_coords', parallel=True).sel(valid_time=slice(t1,t2))
    print(ds)

    # To do , interpolate all fields in the dataset to the xc,yc grid
    ds_interp = ds.interp(longitude=xc, latitude=yc, method='cubic')

    d2m = ds_interp["d2m"] - 273.15 # Convert from Kelvin to Celsius
    # Calculate specific humidity
    ds_interp['q'] = specific_humidity_from_dewpoint( ds_interp['msl']* units.Pa, d2m * units.degC) #.to('kg/kg')

    print(ds_interp)
    # Write fields to binary files
    with open(os.path.join(simulation_input_dir, 'u10.bin'), 'wb') as f:
        ds_interp['u10'].values.astype('>f4').tofile(f)

    with open(os.path.join(simulation_input_dir, 'v10.bin'), 'wb') as f:
        ds_interp['v10'].values.astype('>f4').tofile(f)

    with open(os.path.join(simulation_input_dir, 't2m.bin'), 'wb') as f:
        ds_interp['t2m'].values.astype('>f4').tofile(f)

    with open(os.path.join(simulation_input_dir, 'q2m.bin'), 'wb') as f:
        ds_interp['q'].values.astype('>f4').tofile(f)

    with open(os.path.join(simulation_input_dir, 'avg_sdswrf.bin'), 'wb') as f:
        ds_interp['avg_sdswrf'].values.astype('>f4').tofile(f)

    with open(os.path.join(simulation_input_dir, 'avg_snlwrf.bin'), 'wb') as f:
        ds_interp['avg_snlwrf'].values.astype('>f4').tofile(f)

    with open(os.path.join(simulation_input_dir, 'tp.bin'), 'wb') as f:
        ds_interp['tp'].values.astype('>f4').tofile(f)

    data_cheapaml = f"""
# cheapaml parameters
 &CHEAPAML_CONST
 cheapaml_ntim = 5,
 cheapaml_mask_width=5,
 cheapaml_h = 1000.0,
 cheapaml_kdiff = 1000.0,
# cheapaml_taurelax = 0.1,
# cheapaml_taurelaxocean = 0.0
 &end
# Forcing Files 
 &CHEAPAML_PARM01
 UWindFile='u10.box',
 VWindFile='v10.box',
 SolarFile='avg_sdswrf.box',
 TrFile='t2m.box',
 AirTempFile='t2m.box',
 QrFile='q2m.box',
 AirQFile='q2m.box',
 cheap_dlwfile='avg_snlwrf.box'
 cheap_prfile='tp.box'
 periodicExternalForcing_cheap=.TRUE.,
 externForcingPeriod_cheap=21600.0,
 externForcingCycle_cheap=31536000.0,
 &end
# Formulation parameters
 &CHEAPAML_PARM02
 useFreshWaterFlux=.TRUE.,
 FluxFormula='COARE3',
 useFluxLimit=.TRUE.,
 usetimevarblh=.FALSE.,
 useclouds=.FALSE.,
 usedlongwave=.TRUE.,
 usePrecip=.TRUE.,
 &end
"""
    
if __name__ == "__main__":
    main()