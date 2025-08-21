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
if [ -d $spectre_cwd/build ]; then
  rm -rf $spectre_cwd/build
fi 

mkdir -p $spectre_cwd/build
cd $spectre_cwd/build/
$spectre_mitgcm_source_code/tools/genmake2 -rootdir=$spectre_mitgcm_source_code -mods=$spectre_model_code -ds -mpi -optfile $spectre_optfile
make depend
make -j 2
cd ../

# Copy executable to exe directory
mkdir -p $spectre_model_exe_dir
cp -p ./build/mitgcmuv $spectre_model_exe_dir/mitgcmuv
cp -p ./build/Makefile $spectre_model_exe_dir/Makefile
