#!/bin/bash
#SBATCH -n1
#SBATCH -c32
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_cheapaml
#SBATCH --output=./spectre_cheapaml.out
#SBATCH --error=./spectre_cheapaml.out


SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
source $SCRIPT_DIR/env.sh

###############################################################################################
# Run the script to download make the cheapaml boundary conditions
###############################################################################################
srun --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${SCRIPT_DIR}/../:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_cheapaml_conditions.py /workspace/etc/config.yaml
