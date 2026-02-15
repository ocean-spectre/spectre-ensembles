#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_ics
#SBATCH --output=./spectre_ics.out
#SBATCH --error=./spectre_ics.out


HOST_DATADIR=/group/tdgs/joe/spectre-150-ensembles/glorysv12-curvilinear-15year
###############################################################################################
# Run the script to download ERA5 data
###############################################################################################
srun --container-image=ghcr.io/ocean-spectre/spectre-150-ensembles/spectre-utils:latest \
     --container-mounts=$(pwd):/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_initial_conditions.py /workspace/etc/config.yaml

###############################################################################
