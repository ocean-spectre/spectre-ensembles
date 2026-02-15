#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_ics
#SBATCH --output=./spectre_ics.out
#SBATCH --error=./spectre_ics.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ${spectre_ensembles}/spectre_utils/mk_initial_conditions.py ${spectre_ensembles}/etc/glorys-1-12.yaml

###############################################################################
