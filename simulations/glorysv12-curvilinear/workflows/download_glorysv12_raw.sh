#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=noether
#SBATCH --job-name=spectre_glorysv12_raw
#SBATCH --output=./spectre_glorysv12_raw.out
#SBATCH --error=./spectre_glorysv12_raw.out


if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command' )
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
else
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
fi

source $SCRIPT_DIR/env.sh

###############################################################################################
# Run the script to download Glorysv12 data
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/download_glorys12_raw.py /workspace/etc/config.yaml
