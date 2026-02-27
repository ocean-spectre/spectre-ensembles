#!/bin/bash

# Path where downloaded data is stored
export HOST_DATADIR=/mnt/beegfs/spectre-150-ensembles/glorysv12-curvilinear-15year
export SPECTRE_UTILS_IMG="docker://ghcr.io#ocean-spectre/spectre-ensembles/spectre-utils:sha-6f41db5"
export MITGCM_BASE_IMG="docker://ghcr.io#fluidnumerics/mitgcm-containers/gcc-openmpi:latest"
