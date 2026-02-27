#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --job-name=spectre_ics
#SBATCH --output=./spectre_ics.out
#SBATCH --error=./spectre_ics.out

if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command' )
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
else
    # Fallback for when running the script outside of a Slurm job
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
fi

source $SCRIPT_DIR/env.sh

echo "======================================="
echo ""
echo " Using host data directory : ${HOST_DATADIR}"
echo " Using spectre utils image : ${SPECTRE_UTILS_IMG}"
echo ""
echo "======================================="

###############################################################################################
# Run the script to download ERA5 data
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_initial_conditions.py /workspace/etc/config.yaml

###############################################################################
