#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=noether
#SBATCH --job-name=spectre_era5
#SBATCH --output=./spectre_era5-%A.out
#SBATCH --error=./spectre_era5-%A.out


HOST_DATADIR=/group/tdgs/joe/spectre-150-ensembles/glorysv12-curvilinear-15year
###############################################################################################
# Run the script to download ERA5 data
###############################################################################################
srun --container-image=ghcr.io/ocean-spectre/spectre-150-ensembles/spectre-utils:latest \
     --container-mounts=$(pwd):/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/download_era5.py /workspace/etc/config.yaml

###############################################################################
