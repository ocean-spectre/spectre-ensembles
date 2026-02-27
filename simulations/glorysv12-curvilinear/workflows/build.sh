#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_glorysv12_build
#SBATCH --output=%x-%A.out
#SBATCH --error=%x-%A.out


if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command' )
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
    SIMULATION_DIR=$(dirname $SCRIPT_DIR)
else
    # Fallback for when running the script outside of a Slurm job
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
fi

source $SCRIPT_DIR/env.sh

echo "======================================="
echo ""
echo " Using simulation directory : ${SIMULATION_DIR}"
echo " Using MITgcm base image    : ${MITGCM_BASE_IMG}"
echo ""
echo "======================================="

###############################################################################################
# Run the script to build the mitgcm
###############################################################################################

srun --container-image=$MITGCM_BASE_IMG \
     --container-mounts=$SIMULATION_DIR:/workspace:rw \
     --container-writable \
     /bin/bash -c "source /opt/spack-environment/activate.sh && /opt/util/build.sh"

###############################################################################
