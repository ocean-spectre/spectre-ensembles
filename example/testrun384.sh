#!/bin/bash
##-- Job Name
#PBS -N MITgcm_384
##-- Project code
#PBS -A UFSU0023
#PBS -l walltime=3:00:00
#PBS -l job_priority=economy
#PBS -q main
#PBS -l select=6:ncpus=64:mpiprocs=64:mem=196GB
#PBS -m abe
#PBS -M garrett@fluidnumerics.com

#-- load appropriate modules --
# (example for Derecho-NCAR)
module load ncarenv/24.12 intel-oneapi/2024.2.1 cray-mpich/8.1.29 hdf5/1.12.3 netcdf/4.9.2
echo "----------------------------"
module list
echo "----------------------------"

simulation_template='mitgcm50_z75'  #TODO: Set your simulation template here!
rank_count=384
ensemble_root='simulations'
rundir='testrun_6node'              # can be set to member id
cwd='/glade/work/gbyrd/spectre-150' # this repository's root directory

nranks_per_node=64
ndepth=1

exedir=$cwd/exe/$simulation_template/$rank_count
simdir=$cwd/$ensemble_root/$simulation_template/$rank_count/$rundir
template_input=$cwd/$ensemble_root/$simulation_template/input
mitgcm=$exedir/mitgcmuv

echo "Using executable     : $mitgcm"
echo "Using template input : $template_input"
echo "Simulation directory : $simdir"



#TODO: Verify template_input exists
mkdir -p $simdir

#### Link up input fields ##
ln -s $template_input/* $simdir/
ln -s $exedir/mitgcmuv $simdir/mitgcmuv
