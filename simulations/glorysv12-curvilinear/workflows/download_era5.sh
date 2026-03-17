#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=noether
#SBATCH --job-name=spectre_era5
#SBATCH --output=./spectre_era5-%A.out
#SBATCH --error=./spectre_era5-%A.out


if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command' )
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
    SIMULATION_DIR=$(dirname $SCRIPT_DIR)
else
    # Fallback for when running the script outside of a Slurm job
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
fi

source $SCRIPT_DIR/env.sh

###############################################################################################
# Run the script to download ERA5 data
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${HOME}:${HOME},${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/download_era5.py /workspace/etc/config.yaml

###############################################################################
