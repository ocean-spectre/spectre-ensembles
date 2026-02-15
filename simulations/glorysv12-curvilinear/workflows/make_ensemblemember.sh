#!/bin/bash
#SBATCH -n1
#SBATCH -c12
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_cheapaml
#SBATCH --output=./spectre_cheapaml.out
#SBATCH --error=./spectre_cheapaml.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list
conda env list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ${spectre_ensembles}/spectre_utils/mk_cheapaml_conditions.py ${spectre_ensembles}/etc/glorys-v12.yaml

###############################################################################
#!/bin/bash
#SBATCH -n1
#SBATCH -c64
#SBATCH --mem=240G
#SBATCH --exclusive
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_bcs
#SBATCH --output=./spectre_bcs.out
#SBATCH --error=./spectre_bcs.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list
conda env list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ${spectre_ensembles}/spectre_utils/mk_ocean_boundary_conditions.py ${spectre_ensembles}/etc/glorys-v12.yaml

###############################################################################
#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=franklin
#SBATCH --job-name=spectre_ics
#SBATCH --output=./spectre_ics.out
#SBATCH --error=./spectre_ics.out


###############################################################################################
#   Setup the software environment
###############################################################################################
source ./galapagos_env.sh 
module list
conda env list

###############################################################################################
# Run the script to generate ocean boundary conditions
###############################################################################################
python ${spectre_ensembles}/spectre_utils/mk_initial_conditions.py ${spectre_ensembles}/etc/glorys-1-12.yaml

###############################################################################
