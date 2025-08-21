#!/bin/bash
#
#


# Usage: ./build_mitgcm.sh -e myenvfile.env

usage() {
    echo "Usage: $0 -e <envfile>"
    exit 1
}

# Parse arguments
while getopts "e:" opt; do
  case "$opt" in
    e) ENVFILE="$OPTARG" ;;
    *) usage ;;
  esac
done

# Require envfile argument
if [ -z "$ENVFILE" ]; then
    usage
fi

# Check file exists
if [ ! -f "$ENVFILE" ]; then
    echo "Error: Environment file '$ENVFILE' not found."
    exit 1
fi

# Source the environment file
echo "Sourcing environment file: $ENVFILE"
# shellcheck source=/dev/null
source "$ENVFILE"

# Example: show one of the vars
echo "============================"
echo "Loaded ENV VARS"
echo "----------------------------"
env | grep "spectre_"
echo "============================"
echo "Loaded Modules"
echo "----------------------------"
module list
echo "----------------------------"

# COMPILE
mkdir -p $cwd/build

cd $cwd/build/
rm -rf ./*
$spectre_dirModel/tools/genmake2 -rootdir=$spectre_dirModel -mods=$cwd/$ensemble_root/$simulation_template/$rank_count/code -ds -mpi -optfile $cwd/opt/$optfile
make depend
make -j 2
cd ../

# Copy executable to exe directory
mkdir -p $cwd/exe/$simulation_template/$rank_count
cp -p ./build/mitgcmuv ./exe/$simulation_template/$rank_count/mitgcmuv
cp -p ./build/Makefile ./exe/$simulation_template/$rank_count/Makefile
