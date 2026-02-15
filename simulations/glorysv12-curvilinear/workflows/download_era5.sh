#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=noether
#SBATCH --job-name=spectre_era5
#SBATCH --output=./spectre_era5-%A.out
#SBATCH --error=./spectre_era5-%A.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list
conda env list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ${spectre_ensembles}/spectre_utils/download_era5.py ${spectre_ensembles}/etc/glorys-v12.yaml

###############################################################################
