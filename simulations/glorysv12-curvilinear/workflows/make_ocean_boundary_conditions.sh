#!/bin/bash
#SBATCH -n1
#SBATCH -c64
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_bcs
#SBATCH --output=./spectre_bcs.out
#SBATCH --error=./spectre_bcs.out


SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source $SCRIPT_DIR/env.sh

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_ocean_boundary_conditions.py /workspace/etc/config.yaml

###############################################################################
