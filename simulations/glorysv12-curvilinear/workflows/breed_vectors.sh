#!/bin/bash
#SBATCH --array=1-50
#SBATCH -n64
#SBATCH -c1
#SBATCH --time=12:00:00
#SBATCH --job-name=spectre_breed
#SBATCH --output=breed_%A_%a.out
#SBATCH --error=breed_%A_%a.out

# Each array task runs one breeding member.
# SLURM_ARRAY_TASK_ID = member number (1-50)

MEMBER_ID=$(printf "%03d" $SLURM_ARRAY_TASK_ID)
MEMBER_DIR="ensemble/member_${MEMBER_ID}"

if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command')
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
    SIMULATION_DIR=$(dirname $SCRIPT_DIR)
else
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
    SIMULATION_DIR=$(dirname $SCRIPT_DIR)
fi

source $SCRIPT_DIR/env.sh

echo "======================================="
echo " Breeding member: ${MEMBER_ID}"
echo " Simulation dir:  ${SIMULATION_DIR}"
echo " Member dir:      ${MEMBER_DIR}"
echo "======================================="

# Read nIter0 for this member
NITER0=$(cat ${SIMULATION_DIR}/${MEMBER_DIR}/nIter0.txt)
echo "Starting from iteration: ${NITER0}"

###############################################################################
# Set up member run directory if needed
###############################################################################
if [[ ! -d "${SIMULATION_DIR}/${MEMBER_DIR}/run" ]]; then
    echo "Setting up member run directory..."
    mkdir -p ${SIMULATION_DIR}/${MEMBER_DIR}/run

    # Symlink input files from the main input directory
    for f in ${SIMULATION_INPUT_DIR}/*; do
        ln -sf $f ${SIMULATION_DIR}/${MEMBER_DIR}/run/$(basename $f)
    done

    # Symlink namelist files
    for f in data data.cal data.exf data.kpp data.mnc data.obcs data.pkg data.diagnostics eedata; do
        ln -sf ${SIMULATION_INPUT_DIR}/$f ${SIMULATION_DIR}/${MEMBER_DIR}/run/$f 2>/dev/null
    done

    # Override pickup with the member's perturbed pickup
    ln -sf ${SIMULATION_DIR}/${MEMBER_DIR}/pickup.*.data ${SIMULATION_DIR}/${MEMBER_DIR}/run/
    ln -sf ${SIMULATION_DIR}/${MEMBER_DIR}/pickup.*.meta ${SIMULATION_DIR}/${MEMBER_DIR}/run/

    # Create a member-specific data file with correct nIter0 and nTimeSteps
    sed "s/nIter0=.*/nIter0=${NITER0},/" ${SIMULATION_INPUT_DIR}/data > ${SIMULATION_DIR}/${MEMBER_DIR}/run/data

    echo "Done."
fi

###############################################################################
# Run MITgcm for this member
###############################################################################
cd ${SIMULATION_DIR}/${MEMBER_DIR}/run

srun --mpi=pmix \
     --container-image=$MITGCM_BASE_IMG \
     --container-mounts=${SIMULATION_INPUT_DIR}:/input,${SIMULATION_DIR}:/workspace:rw \
     --container-env=MEMBER_DIR,NITER0 \
     /opt/mitgcm/mitgcmuv
