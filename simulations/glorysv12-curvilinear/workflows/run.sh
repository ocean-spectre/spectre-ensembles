#!/bin/bash
#SBATCH -n64
#SBATCH -c1
#SBATCH --job-name=spectre_glorysv12_run
#SBATCH --output=%x-%A.out
#SBATCH --error=%x-%A.out

export RUN_DIR="demo/"

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
echo " Using run directory        : ${RUN_DIR}"
echo " Using MITgcm base image    : ${MITGCM_BASE_IMG}"
echo ""
echo "======================================="

###############################################################################
# Set up run directory
###############################################################################
if [[ ! -d "$RUN_DIR" ]]; then
  echo "-------------------------------------"
  echo "  > Directory $RUN_DIR does not exist. Setting up the run directory now..."
  echo ""
  srun --ntasks=1 \
       --mpi=pmix \
       --container-image=$MITGCM_BASE_IMG \
       --container-mounts=$SIMULATION_DIR:/workspace:rw \
       --container-env=RUN_DIR \
       /bin/bash -c /workspace/workflows/run_setup.sh
  echo ""
  echo "  > Done setting up the run directory!"
  echo ""
  echo "-------------------------------------"
fi

###############################################################################
# Launch mitgcm under enroot container
###############################################################################
srun --mpi=pmix \
     --container-image=$MITGCM_BASE_IMG \
     --container-mounts=$SIMULATION_DIR:/workspace:rw \
     --container-env=RUN_DIR \
     /bin/bash -c /workspace/workflows/run_worker.sh
