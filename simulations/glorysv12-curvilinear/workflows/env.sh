#!/bin/bash

# Path where downloaded data is stored
export HOST_DATADIR=/mnt/beegfs/spectre-150-ensembles/simulations/glorysv12-curvilinear/downloads
export SPECTRE_UTILS_IMG="docker://ghcr.io#ocean-spectre/spectre-ensembles/spectre-utils:main"
export MITGCM_BASE_IMG="docker://ghcr.io#fluidnumerics/mitgcm-containers/gcc-openmpi:latest"
