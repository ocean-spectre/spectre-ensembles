#!/bin/bash
#SBATCH -N1
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
conda env list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ./spectre_utils/mk_ocean_boundary_conditions.py ./etc/glorys-1-12.yaml

###############################################################################