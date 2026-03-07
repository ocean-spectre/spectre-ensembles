#!/bin/bash
#SBATCH -n1
#SBATCH -c32
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_exf
#SBATCH --output=./spectre_exf.out
#SBATCH --error=./spectre_exf.out

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
# Run the script to download make the exf boundary conditions
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_exf_conditions.py /workspace/etc/config.yaml
