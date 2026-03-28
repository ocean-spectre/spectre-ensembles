#!/bin/bash
#SBATCH --array=1-50
#SBATCH -n1
#SBATCH -c4
#SBATCH --time=12:00:00
#SBATCH --job-name=spectre_ens_plot
#SBATCH --output=ens_plot_%A_%a.out
#SBATCH --error=ens_plot_%A_%a.out

# Each array task plots surface fields for one ensemble member.
# SLURM_ARRAY_TASK_ID = member number (1-50)

MEMBER_ID=$(printf "%03d" $SLURM_ARRAY_TASK_ID)

if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command')
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
    SIMULATION_DIR=$(dirname $SCRIPT_DIR)
else
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
    SIMULATION_DIR=$(dirname $SCRIPT_DIR)
fi

source $SCRIPT_DIR/env.sh

MEMBER_RUN_DIR="${SIMULATION_DIR}/ensemble/member_${MEMBER_ID}/run"

echo "Plotting surface fields for member ${MEMBER_ID}"
echo "Run dir: ${MEMBER_RUN_DIR}"

srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${HOME}:${HOME},${SIMULATION_DIR}:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/plot_surface_fields.py \
       /workspace/ensemble/member_${MEMBER_ID}/run \
       --plots-dir /workspace/ensemble/member_${MEMBER_ID}/run/plots \
       --poll 120 \
       --start-date 2002-07-01 \
       --dt 360.0
