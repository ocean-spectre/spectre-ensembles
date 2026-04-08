#!/bin/bash
#SBATCH -n1
#SBATCH -c4
#SBATCH --time=3-00:00:00
#SBATCH --job-name=spectre_postproc
#SBATCH --output=%x-%A.out
#SBATCH --error=%x-%A.out

# Post-processor: runs the binary→NetCDF converter and surface field plotter
# as background job steps. Runs until walltime or failure.

if [ -n "${SLURM_JOB_ID:-}" ]; then
    SCRIPT_PATH=$(scontrol show job "$SLURM_JOB_ID" --json | jq -r '.jobs[0].command')
    SCRIPT_DIR=$(dirname "$(readlink -f "$SCRIPT_PATH")")
    SIMULATION_DIR="${SIMULATION_DIR:-$(dirname $SCRIPT_DIR)}"
else
    SCRIPT_DIR=$(dirname "$(readlink -f "$0")")
    SIMULATION_DIR="${SIMULATION_DIR:-$(dirname $SCRIPT_DIR)}"
fi

source $SCRIPT_DIR/env.sh

echo "======================================="
echo " Post-processor"
echo " Simulation dir: ${SIMULATION_DIR}"
echo " SLURM Job ID:   ${SLURM_JOB_ID}"
echo "======================================="

# Step 1: Converter (binary diagnostics → per-tile NetCDF)
srun --ntasks=1 --cpus-per-task=2 --exclusive \
     --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${HOME}:${HOME},${SIMULATION_DIR}:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/convert_diagnostics_to_netcdf.py \
       /workspace \
       --poll 60 \
       --start-date 2002-07-01 \
       --dt 360.0 &
CONVERTER_PID=$!
echo "Converter started: srun PID $CONVERTER_PID"

# Step 2: Plotter (reads NetCDF, writes surface field PNGs)
srun --ntasks=1 --cpus-per-task=2 --exclusive \
     --container-image=$SPECTRE_UTILS_IMG \
     --container-mounts=${HOME}:${HOME},${SIMULATION_DIR}:/workspace,${HOST_DATADIR}:/data \
     python /opt/spectre_utils/plot_surface_fields.py \
       /workspace \
       --poll 120 \
       --start-date 2002-07-01 \
       --dt 360.0 &
PLOTTER_PID=$!
echo "Plotter started: srun PID $PLOTTER_PID"

# Wait for either to exit — if one fails, kill the other
wait -n $CONVERTER_PID $PLOTTER_PID
EXIT_CODE=$?
echo "A job step exited with code $EXIT_CODE"

# Clean up the other
kill $CONVERTER_PID $PLOTTER_PID 2>/dev/null
wait

echo "Post-processor finished"
exit $EXIT_CODE
