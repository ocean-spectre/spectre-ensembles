#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_glorysv12_build
#SBATCH --output=%x-%A.out
#SBATCH --error=%x-%A.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list
conda env list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
$(pwd)/../build-mitgcm.sh -e $(pwd)/../../env/galapagos-franklin-glorysv12-curvilinear.sh
###############################################################################
