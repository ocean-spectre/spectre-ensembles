#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=noether
#SBATCH --job-name=spectre_glorysv12_raw
#SBATCH --output=./spectre_glorysv12_raw.out
#SBATCH --error=./spectre_glorysv12_raw.out


HOST_DATADIR=/group/tdgs/joe/spectre-150-ensembles/glorysv12-curvilinear-15year

###############################################################################################
# Run the script to download Glorysv12 data
###############################################################################################
srun --container-image=ghcr.io/ocean-spectre/spectre-150-ensembles/spectre-utils:latest \
     --container-mounts=$(pwd):/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/download_glorys12_raw.py /workspace/etc/config.yaml
