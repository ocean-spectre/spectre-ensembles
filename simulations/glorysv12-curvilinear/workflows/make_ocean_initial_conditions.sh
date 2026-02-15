#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_ics
#SBATCH --output=./spectre_ics.out
#SBATCH --error=./spectre_ics.out


SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source $SCRIPT_DIR/env.sh

###############################################################################################
# Run the script to download ERA5 data
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_initial_conditions.py /workspace/etc/config.yaml

###############################################################################
