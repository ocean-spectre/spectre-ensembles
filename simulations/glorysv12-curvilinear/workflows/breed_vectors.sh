#!/bin/bash
#SBATCH --array=1-50
#SBATCH -n64
#SBATCH -c1
#SBATCH --time=12:00:00
#SBATCH --job-name=spectre_breed
#SBATCH --output=breed_%A_%a.out
#SBATCH --error=breed_%A_%a.out

# Each array task runs one breeding member for one 30-day cycle.
# SLURM_ARRAY_TASK_ID = member number (1-50)
#
# Each member starts from nIter0=0 with its own perturbed IC files
# (T.init.bin, S.init.bin, U.init.bin, V.init.bin, Eta.init.bin)
# and runs forward for nTimeSteps (default 7200 = 30 days at dt=360s).
#
# The perturbed ICs are created/updated by breed_vectors.py (init or rescale).

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

MEMBER_DIR="${SIMULATION_DIR}/ensemble/member_${MEMBER_ID}"
MEMBER_RUN_DIR="${MEMBER_DIR}/run"
NTIMESTEPS=${BREED_NTIMESTEPS:-7200}
IC_FILES="T.init.bin S.init.bin U.init.bin V.init.bin Eta.init.bin"

echo "======================================="
echo " Breeding member: ${MEMBER_ID}"
echo " nIter0:          0"
echo " nTimeSteps:      ${NTIMESTEPS}"
echo "======================================="

###############################################################################
# Set up member run directory (fresh each cycle)
###############################################################################
rm -rf ${MEMBER_RUN_DIR}
mkdir -p ${MEMBER_RUN_DIR}

# Symlink all files from the master input directory
for f in ${SIMULATION_INPUT_DIR}/*; do
    ln -sf $f ${MEMBER_RUN_DIR}/$(basename $f)
done

# Remove symlinks for IC files — these will be member-specific copies
for f in ${IC_FILES}; do
    rm -f ${MEMBER_RUN_DIR}/$f
done

# Copy member's perturbed IC files (created by breed_vectors.py)
for f in ${IC_FILES}; do
    if [[ -f ${MEMBER_DIR}/$f ]]; then
        cp ${MEMBER_DIR}/$f ${MEMBER_RUN_DIR}/$f
    else
        echo "WARNING: ${MEMBER_DIR}/$f not found"
    fi
done

# Copy namelist files from beegfs (latest config, not stale local copy)
for f in data.cal data.exf data.kpp data.mnc data.obcs data.pkg data.diagnostics eedata; do
    cp ${SIMULATION_DIR}/input/$f ${MEMBER_RUN_DIR}/$f 2>/dev/null
done

# Generate member-specific 'data' file:
#   nIter0=0, nTimeSteps=NTIMESTEPS, single pickup at end
CYCLE_SECONDS=$((NTIMESTEPS * 360))
cat ${SIMULATION_DIR}/input/data | \
    sed -e "s/^ nIter0=.*/ nIter0=0,/" \
        -e "s/^ endTime=.*/ nTimeSteps=${NTIMESTEPS},/" \
        -e "s/^ pChkptFreq=.*/ pChkptFreq=${CYCLE_SECONDS}.0,/" \
        -e "s/^ chkptFreq=.*/ chkptFreq=0.0,/" \
        -e "s/^ dumpFreq=.*/ dumpFreq=0.0,/" \
    > ${MEMBER_RUN_DIR}/data

echo "--- Member data file (key params) ---"
grep -E '^ nIter0|^ nTimeSteps|^ pChkptFreq|^ chkptFreq|^ deltaT|^ dumpFreq' ${MEMBER_RUN_DIR}/data
echo "--------------------------------------"

###############################################################################
# Run MITgcm
###############################################################################
cd ${MEMBER_RUN_DIR}

srun --mpi=pmix \
     --container-image=$MITGCM_BASE_IMG \
     --container-mounts=${SIMULATION_INPUT_DIR}:/input:ro,${SIMULATION_DIR}:/workspace:rw \
     /opt/mitgcm/mitgcmuv
