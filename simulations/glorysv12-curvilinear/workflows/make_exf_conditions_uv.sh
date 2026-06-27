#!/bin/bash
#SBATCH -n1
#SBATCH -c16
#SBATCH --mem=64G
#SBATCH --job-name=spectre_exf_uv
#SBATCH --output=./spectre_exf_uv-%A.out
#SBATCH --error=./spectre_exf_uv-%A.out
#SBATCH --time=2-00:00:00

set -euo pipefail

if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command')
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
else
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
fi

SIMULATION_DIR=$(dirname "$SCRIPT_DIR")
REPO_DIR=$(realpath "$SIMULATION_DIR/../..")

source "$SCRIPT_DIR/env.sh"

###############################################################################
# Build EXF atmosphere binaries on bare metal via uv, using the local
# spectre_utils checkout (which contains the inclusive-end-of-day slicing fix
# in mk_exf_conditions.py that the container image does not yet have).
#
# The python script reads container paths from config.yaml
# (working_directory: /data, simulation_directory: /workspace). On bare metal
# those don't exist, so substitute the real host paths into a temp config:
#   working_directory   -> $HOST_DATADIR  (ERA5 NetCDF inputs)
#   simulation_directory-> $SIMULATION_DIR (outputs go to <sim>/input)
###############################################################################
cd "$REPO_DIR"

TMP_CONFIG=$(mktemp --suffix=.yaml)
trap 'rm -f "$TMP_CONFIG"' EXIT
sed -e "s|^working_directory:.*|working_directory: ${HOST_DATADIR}|" \
    -e "s|^simulation_directory:.*|simulation_directory: ${SIMULATION_DIR}|" \
    "$SIMULATION_DIR/etc/config.yaml" > "$TMP_CONFIG"

uv run --project "$REPO_DIR" python "$REPO_DIR/spectre_utils/mk_exf_conditions.py" "$TMP_CONFIG"
