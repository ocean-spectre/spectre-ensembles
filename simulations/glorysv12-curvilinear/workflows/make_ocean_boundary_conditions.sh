#!/bin/bash
#SBATCH -n1
#SBATCH -c64
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_bcs
#SBATCH --output=./spectre_bcs.out
#SBATCH --error=./spectre_bcs.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ${spectre_ensembles}/spectre_utils/mk_ocean_boundary_conditions.py ${spectre_ensembles}/etc/glorys-v12.yaml

###############################################################################
