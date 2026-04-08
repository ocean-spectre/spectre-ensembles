#!/bin/bash
# repeat_year_run.sh — SLURM job script for one year of a repeat-year chain.
#
# Expected environment variables (set by repeat_year_chain.sh via --export):
#   RUN_NUM         — zero-padded run number (001–050)
#   EXPERIMENT      — experiment subdirectory name (e.g. repeat-year-50)
#   SIMULATION_DIR  — absolute path to simulations/glorysv12-curvilinear
#   PREV_RUN_NUM    — previous run number (empty for run 001)
#
# The script:
#   1. Creates the run directory with symlinks to input/
#   2. For runs > 001: converts the previous run's pickup to init files
#   3. Launches MITgcm (64-rank MPI)

set -euo pipefail

if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command' )
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
else
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
fi
source "$SCRIPT_DIR/env.sh"

REPO_ROOT=$(readlink -f "$SIMULATION_DIR/../..")
RUN_DIR="${EXPERIMENT}/${RUN_NUM}"
ITER_FINAL="0000087600"

echo "======================================="
echo ""
echo " Repeat-year experiment : ${EXPERIMENT}"
echo " Run number             : ${RUN_NUM}"
echo " Run directory          : ${RUN_DIR}"
echo " Simulation directory   : ${SIMULATION_DIR}"
echo " MITgcm image           : ${MITGCM_BASE_IMG}"
echo " SLURM Job ID           : ${SLURM_JOB_ID:-none}"
echo ""
echo "======================================="

# Write SLURM job ID for dashboard discovery
mkdir -p "${SIMULATION_DIR}/${RUN_DIR}"
echo "${SLURM_JOB_ID:-}" > "${SIMULATION_DIR}/${RUN_DIR}/slurm_job_id"

###############################################################################
# Step 1: Set up run directory — symlink all input files
###############################################################################
echo "--- Setting up run directory ---"
srun --ntasks=1 \
     --mpi=pmix \
     --container-image=$MITGCM_BASE_IMG \
     --container-mounts=$SIMULATION_DIR:/workspace:rw \
     --container-env=RUN_DIR \
     /bin/bash -c "mkdir -p /workspace/$RUN_DIR && ln -sf /workspace/input/* /workspace/$RUN_DIR/"

echo "  > Symlinks created."

###############################################################################
# Step 1b: Copy experiment-level override files (e.g. data.exf) into run dir
###############################################################################
OVERRIDE_DIR="${SIMULATION_DIR}/${EXPERIMENT}"
if compgen -G "${OVERRIDE_DIR}/data*" > /dev/null 2>&1; then
    echo "--- Applying overrides from ${EXPERIMENT}/ ---"
    for f in "${OVERRIDE_DIR}"/data*; do
        fname=$(basename "$f")
        dest="${SIMULATION_DIR}/${RUN_DIR}/${fname}"
        rm -f "$dest"
        cp "$f" "$dest"
        echo "  > Copied override: ${fname}"
    done
fi

###############################################################################
# Step 2: For runs after 001, convert previous pickup to init files
###############################################################################
if [[ -n "${PREV_RUN_NUM:-}" ]]; then
    PREV_DIR="${EXPERIMENT}/${PREV_RUN_NUM}"
    PICKUP_PREFIX="${PREV_DIR}/pickup.${ITER_FINAL}"

    echo "--- Converting pickup from run ${PREV_RUN_NUM} ---"
    echo "  Pickup: ${PICKUP_PREFIX}"
    echo "  Output: ${RUN_DIR}/"

    srun --ntasks=1 \
         --mpi=pmix \
         --container-image=$SPECTRE_UTILS_IMG \
         --container-mounts=${REPO_ROOT}:/repo:rw \
         /bin/bash -c "cd /repo && python spectre_utils/pickup_to_init.py \
             simulations/glorysv12-curvilinear/${PICKUP_PREFIX} \
             simulations/glorysv12-curvilinear/${RUN_DIR}/ \
             --nx 768 --ny 424 --nr 50"

    echo "  > Init files created from pickup."
fi

###############################################################################
# Step 3: Launch MITgcm
###############################################################################
echo "--- Launching MITgcm ---"
srun --mpi=pmix \
     --cpu-bind=cores \
     --container-image=$MITGCM_BASE_IMG \
     --container-mounts=$SIMULATION_DIR:/workspace:rw \
     --container-env=RUN_DIR \
     /bin/bash -c "source /opt/spack-environment/activate.sh && cd /workspace/$RUN_DIR && /workspace/exe/mitgcmuv"

echo "--- Run ${RUN_NUM} complete ---"
