#!/bin/bash

cwd=$(pwd)
optfile='derecho'
simulation_template='mitgcm50_z75' #TODO: Set your simulation template here!
rank_count=192
ensemble_root='simulations'



################################## DO NOT MODIFY BELOW ####################################
#               (unless you really know what you're doing....)
###########################################################################################

dirModel="${cwd}/MITgcm"

#-- load appropriate modules --
# (example for Derecho-NCAR)
module --force purge
module load ncarenv/24.12 intel-oneapi/2024.2.1 cray-mpich/8.1.29 hdf5/1.12.3 netcdf/4.9.2 
#hdf5-mpi/1.12.3 netcdf-mpi/4.9.2

echo "----------------------------"
module list
echo "----------------------------"

# COMPILE
mkdir -p $cwd/build

cd $cwd/build/
rm -rf ./*
$dirModel/tools/genmake2 -rootdir=$dirModel -mods=$cwd/$ensemble_root/$simulation_template/$rank_count/code -ds -mpi -optfile $cwd/opt/$optfile
make depend
make -j 2
cd ../

# Copy executable to exe directory
mkdir -p $cwd/exe/$simulation_template/$rank_count
cp -p ./build/mitgcmuv ./exe/$simulation_template/$rank_count/mitgcmuv
cp -p ./build/Makefile ./exe/$simulation_template/$rank_count/Makefile
