#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=noether
#SBATCH --job-name=spectre_era5
#SBATCH --output=./spectre_era5-%A.out
#SBATCH --error=./spectre_era5-%A.out


SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source $SCRIPT_DIR/env.sh

###############################################################################################
# Run the script to download ERA5 data
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/download_era5.py /workspace/etc/config.yaml

###############################################################################
