#!/bin/bash
#SBATCH -n1
#SBATCH -c64
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_bcs
#SBATCH --output=./spectre_bcs.out
#SBATCH --error=./spectre_bcs.out


HOST_DATADIR=/group/tdgs/joe/spectre-150-ensembles/glorysv12-curvilinear-15year

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
srun --container-image=ghcr.io/ocean-spectre/spectre-150-ensembles/spectre-utils:latest \
     --container-mounts=$(pwd):/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_ocean_boundary_conditions.py /workspace/etc/config.yaml

###############################################################################
