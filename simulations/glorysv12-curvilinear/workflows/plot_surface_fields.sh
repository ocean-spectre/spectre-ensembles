#!/bin/bash
#SBATCH -n1
#SBATCH -c4
#SBATCH --time=3-00:00:00
#SBATCH --job-name=spectre_plot
#SBATCH --output=./spectre_plot.out
#SBATCH --error=./spectre_plot.out

if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command' )
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
    SIMULATION_DIR=$(dirname $SCRIPT_DIR)
else
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
fi

source $SCRIPT_DIR/env.sh

RUN_DIR="${RUN_DIR:-test-run-03252026/}"

srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${HOME}:${HOME},${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/plot_surface_fields.py \
       /workspace/${RUN_DIR} \
       --plots-dir /workspace/${RUN_DIR}/plots \
       --poll 120 \
       --start-date 2002-07-01 \
       --dt 360.0
