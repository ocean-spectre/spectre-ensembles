#!/bin/bash
#SBATCH -n1
#SBATCH -c16
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_obc_check
#SBATCH --output=./spectre_obc_check.out
#SBATCH --error=./spectre_obc_check.out

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
# Run QC review of ocean boundary conditions
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${HOME}:${HOME},${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/review_obc_conditions.py /workspace/etc/config.yaml

###############################################################################################
# Animate ocean boundary conditions
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${HOME}:${HOME},${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/animate_obc_conditions.py /workspace/etc/config.yaml
