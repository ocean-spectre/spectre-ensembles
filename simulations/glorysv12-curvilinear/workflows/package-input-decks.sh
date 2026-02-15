#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_tar
#SBATCH --output=./spectre_tar.out
#SBATCH --error=./spectre_tar.out
###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh
module list
conda env list

###############################################################################################
# Run the script to package the input decks
###############################################################################################
tar -cvzf glorys_v1.12_input_decks.tar.gz ${spectre_ensembles}/simulations/glorysv12/input/
