#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=oram
#SBATCH --job-name=spectre_glorysv12_raw
#SBATCH --output=./spectre_glorysv12_raw.out
#SBATCH --error=./spectre_glorysv12_raw.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list
conda env list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ${spectre_ensembles}/spectre_utils/download_glorys12_raw.py ${spectre_ensembles}/etc/glorys-v12.yaml

###############################################################################
