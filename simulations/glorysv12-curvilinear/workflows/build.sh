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

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################

srun --container-image=ghcr.io/fluidnumerics/mitgcm-containers/gcc-openmpi:latest \
     --container-mounts=$(pwd):/workspace \
     /opt/util/build.sh

###############################################################################
