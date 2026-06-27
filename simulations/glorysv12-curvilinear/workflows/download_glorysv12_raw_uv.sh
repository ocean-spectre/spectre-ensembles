#!/bin/bash
#SBATCH -n1
#SBATCH -c8
#SBATCH --nodelist=noether
#SBATCH --job-name=spectre_glorysv12_raw_uv
#SBATCH --output=./spectre_glorysv12_raw_uv-%A.out
#SBATCH --error=./spectre_glorysv12_raw_uv-%A.out

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
# Run GLORYS raw download on bare metal via uv, using ~/.netrc for auth to
# tds.mercator-ocean.fr. Avoids container rebuild needed to ship credentials.
#
# Mirrors the container script's data layout: writes to $HOST_DATADIR.
###############################################################################
cd "$REPO_DIR"

# Rewrite paths used inside the python script. The script reads
# config['working_directory'] and writes there, so we point it to the host
# downloads dir for this run via a small inline sed-free shim: set env var
# WORKING_DIR_OVERRIDE and patch the script... simpler: just sym-link /data.
#
# The python script reads working_directory from config.yaml as "/data". On
# bare metal that path doesn't exist as a real directory, so we instead pass
# a config copy with the host path substituted.
TMP_CONFIG=$(mktemp --suffix=.yaml)
trap 'rm -f "$TMP_CONFIG"' EXIT
sed "s|^working_directory:.*|working_directory: ${HOST_DATADIR}|" \
    "$SIMULATION_DIR/etc/config.yaml" > "$TMP_CONFIG"

###############################################################################
# The Mercator THREDDS server drops the connection every ~12-15 h
# (ChunkedEncodingError / Read timed out), failing the python process partway
# through. The script resumes by skipping already-downloaded files, so we wrap
# it in a retry loop. Before each attempt we delete any corrupt partial .nc
# (< 1 MB) left by an interrupted write, since the skip-if-exists logic would
# otherwise treat a truncated file as complete. The loop exits 0 on the first
# clean completion, or keeps retrying until the SLURM wall-clock limit kills it.
###############################################################################
# do NOT let a single failed attempt abort the whole script
set +e

MAX_ATTEMPTS=200
RETRY_SLEEP=120
attempt=0
while (( attempt < MAX_ATTEMPTS )); do
    attempt=$((attempt + 1))
    echo "===== download attempt ${attempt} / ${MAX_ATTEMPTS} ($(date)) ====="

    # Purge truncated partials from a previous interrupted attempt.
    find "$HOST_DATADIR" -name 'glorysv12_*_glorys12_raw.*.nc' -size -1M -print -delete

    uv run --project "$REPO_DIR" \
        python "$REPO_DIR/spectre_utils/download_glorys12_raw.py" "$TMP_CONFIG"
    rc=$?

    if (( rc == 0 )); then
        echo "===== download completed cleanly on attempt ${attempt} ($(date)) ====="
        exit 0
    fi

    echo "----- attempt ${attempt} failed (rc=${rc}); retrying in ${RETRY_SLEEP}s -----"
    sleep "$RETRY_SLEEP"
done

echo "!!! exhausted ${MAX_ATTEMPTS} attempts without clean completion" >&2
exit 1
