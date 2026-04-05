#!/bin/bash
# repeat_year_chain.sh — Submit 50 chained repeat-year simulations.
#
# Each simulation runs July 1, 2002 → July 1, 2003 (365 days, nIter0=0).
# After each run completes, the next job converts its pickup file to
# initial conditions and launches a fresh 1-year run.
#
# Usage:
#   cd simulations/glorysv12-curvilinear
#   bash workflows/repeat_year_chain.sh [--dry-run]
#
# Requirements:
#   - The MITgcm data namelist must have nIter0=0, endTime=31536000.0
#   - The data.cal must have startDate_1=20020701
#   - EXF/OBC forcing files must cover the full Jul 2002–Jul 2003 period

set -euo pipefail

SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
SIMULATION_DIR=$(dirname "$SCRIPT_DIR")

N_RUNS=50
EXPERIMENT="repeat-year-50"
DRY_RUN=false

if [[ "${1:-}" == "--dry-run" ]]; then
    DRY_RUN=true
    echo "[DRY RUN] Will print sbatch commands without submitting."
fi

EXPERIMENT_DIR="${SIMULATION_DIR}/${EXPERIMENT}"
mkdir -p "${EXPERIMENT_DIR}"

echo "======================================="
echo " Repeat-year chain: ${N_RUNS} runs"
echo " Experiment dir: ${EXPERIMENT_DIR}"
echo "======================================="

PREV_JOB_ID=""

for i in $(seq 1 $N_RUNS); do
    RUN_NUM=$(printf "%03d" $i)
    PREV_RUN_NUM=""
    if [[ $i -gt 1 ]]; then
        PREV_RUN_NUM=$(printf "%03d" $((i - 1)))
    fi

    SBATCH_ARGS=(
        -n64
        -c1
        --time=3-00:00:00
        --nodelist=franklin
        --job-name="repeat_yr_${RUN_NUM}"
        --output="${EXPERIMENT_DIR}/${RUN_NUM}-%A.out"
        --error="${EXPERIMENT_DIR}/${RUN_NUM}-%A.out"
        --chdir="${SIMULATION_DIR}"
        --export="ALL,RUN_NUM=${RUN_NUM},PREV_RUN_NUM=${PREV_RUN_NUM},EXPERIMENT=${EXPERIMENT},SIMULATION_DIR=${SIMULATION_DIR}"
    )

    if [[ -n "$PREV_JOB_ID" ]]; then
        SBATCH_ARGS+=(--dependency=afterok:${PREV_JOB_ID})
    fi

    if $DRY_RUN; then
        echo "  [${RUN_NUM}] sbatch ${SBATCH_ARGS[*]} ${SCRIPT_DIR}/repeat_year_run.sh"
        PREV_JOB_ID="FAKE_${RUN_NUM}"
    else
        JOB_ID=$(sbatch "${SBATCH_ARGS[@]}" "${SCRIPT_DIR}/repeat_year_run.sh" | awk '{print $NF}')
        echo "  Submitted run ${RUN_NUM}: SLURM job ${JOB_ID}"
        PREV_JOB_ID=$JOB_ID
    fi
done

echo ""
echo "All ${N_RUNS} jobs submitted."
if ! $DRY_RUN; then
    echo "Monitor with:  squeue -u \$USER --name='repeat_yr_*'"
fi
