#!/usr/bin/env python

import numpy as np
import xmitgcm
from spectre_utils import common
import yaml

def get_dataset(simulation_directory, model_delta_t, model_ref_date=None):
    return xmitgcm.open_mdsdataset(simulation_directory, 
                            grid_dir=simulation_directory, 
                            iters='all', 
                            prefix=['U', 'V', 'T', 'S', 'Eta'], 
                            read_grid=True, 
                            delta_t=model_delta_t,
                            ref_date=model_ref_date, 
                            geometry='curvilinear')


def main():
    
    args = common.cli()

    # Load configuration from YAML file
    with open(args.config_file, 'r') as f:
        config = yaml.safe_load(f)

    simulation_directory = config['simulation_directory']
    model_delta_t = 120 # TO DO : Read this from the simulation directory input/data file 
    #model_delta_t = 450 # TO DO : Read this from the simulation directory input/data file 
    model_ref_date = config['domain']['time']['start']

    ds = get_dataset(f"{simulation_directory}", model_delta_t, model_ref_date=model_ref_date)

    #ds.to_netcdf(f"{simulation_directory}/mitgcm.nc")
    ds.to_netcdf(f"mitgcm.nc")

if __name__ == "__main__": 
    main()
