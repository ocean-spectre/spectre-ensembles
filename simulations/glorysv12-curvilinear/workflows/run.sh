#!/bin/bash
#SBATCH -n128
#SBATCH -c1
#SBATCH --mem=64G
#SBATCH --exclusive
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_bcs
#SBATCH --output=./glorysv12_mitgcm_run.out
#SBATCH --error=./glorysv12_mitgcm_run.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list
conda env list

source ${spectre_ensembles}/env/galapagos-franklin-glorysv12-curvilinear.sh

###############################################################################################
#   Setup the environment vars for logging/book-keeping
###############################################################################################

export ENSEMBLE_NAME="test-1y_128"
export JOBID=$SLURM_JOB_ID
export MEMBERID="memb000"
export MON_DBROOT="/group/tdgs/spectre/monitoring/"

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
cd $spectre_model_exe_dir

rm STDOUT.* STDERR.*
mpirun -np ${SLURM_NTASKS} --use-hwthread-cpus ./mitgcmuv &
mitgcm_pid=$!

# Wait for STDOUT.0000 to appear
while [[ ! -s STDOUT.0000 ]]; do sleep 0.2; done

python ${spectre_ensembles}/spectre_utils/mitgcm_mon_tail.py --from-start "${spectre_model_exe_dir}/STDOUT.0000" & 
TAIL_PID=$!

# When the MITgcm exits, give the tailer a few seconds to catch any last lines, then stop
wait $MITGCM_PID
sleep 3
kill $TAIL_PID || true
wait $TAIL_PID 2>/dev/null || true

###############################################################################
