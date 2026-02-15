#!/bin/bash
#SBATCH -n1
#SBATCH -c32
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_cheapaml
#SBATCH --output=./spectre_cheapaml.out
#SBATCH --error=./spectre_cheapaml.out


HOST_DATADIR=/group/tdgs/joe/spectre-150-ensembles/glorysv12-curvilinear-15year
###############################################################################################
# Run the script to download make the cheapaml boundary conditions
###############################################################################################
srun --container-image=ghcr.io/ocean-spectre/spectre-150-ensembles/spectre-utils:latest \
     --container-mounts=$(pwd):/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/mk_cheapaml_conditions.py /workspace/etc/config.yaml
