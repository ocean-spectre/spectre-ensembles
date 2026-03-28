# Bred Vector Ensemble Generation

This directory contains the configuration and member directories for generating
50 independent ensemble initial conditions using the **bred vector method**.

## Methodology

### Why bred vectors?

Ocean models are chaotic — small differences in initial conditions grow
exponentially, projecting onto the system's fastest-growing instability modes.
The bred vector method exploits this by:

1. Perturbing a control state with small noise
2. Running the model forward to let perturbations grow
3. Rescaling the perturbation back to a target amplitude
4. Repeating until the perturbation "locks on" to the dominant growing modes

After several breeding cycles, the perturbations are no longer random noise —
they represent physically meaningful, dynamically balanced uncertainty structures
(Gulf Stream meanders, baroclinic eddies, frontal instabilities). These are
far more realistic initial condition perturbations than random noise alone.

### Breeding cycle

```
Control:    ─────────────────────────────────────────────►
                 │                    │
                 │ perturb            │ rescale & perturb
                 ▼                    ▼
Member i:   ─────●════════════════════●════════════════════●───►
                 cycle 0              cycle 1              cycle 2 ...
                 (30 days)            (30 days)
```

Each cycle:
1. Member starts from `control_state + perturbation`
2. Runs forward for 30 days (configurable)
3. At end: `bred_vector = member_state - control_state`
4. Rescale factor = `target_RMS / actual_RMS` (computed from temperature)
5. **Same rescale factor applied to ALL variables** (T, S, U, V, SSH) to preserve
   geostrophic and hydrostatic balance
6. New perturbation: `control_state + rescale_factor × bred_vector`

### Design choices

**50 independent streams**: Each member has its own random seed and evolves
independently. This maximizes the diversity of growing modes captured.

**Single rescaling factor from temperature**: Rather than rescaling each variable
independently (which would break dynamical consistency), we compute one factor
from the temperature field and apply it uniformly. The bred vector's internal
balance between T, S, U, V, and SSH is preserved.

**Target amplitude 0.05°C RMS**: This is the standard for mesoscale-resolving
North Atlantic ensembles — large enough to seed growing instabilities but small
enough to remain in the linear growth regime.

**30-day cycle length**: Captures mesoscale eddy growth and Gulf Stream
instabilities (Rossby deformation timescale). Shorter cycles (7 days) emphasize
fast barotropic modes; longer cycles (60+ days) allow slower baroclinic modes.
Configurable in `breed_config.yaml`.

**8 breeding cycles**: Empirically sufficient for convergence. Monitor with
`breed_vectors.py status` — the per-variable RMS should stabilize by cycle 5–6.

## Workflow

### Prerequisites

- Completed control spinup run with at least one permanent pickup file
- Set `pickup_iter` in `breed_config.yaml` (or leave null to auto-detect latest)

### Steps

```bash
cd simulations/glorysv12-curvilinear

# 1. Initialize 50 perturbed pickups from the control state
uv run python ../../spectre_utils/breed_vectors.py init ensemble/breed_config.yaml

# 2. Run all 50 members for one breeding cycle (SLURM array job)
sbatch --chdir=$(pwd) workflows/breed_vectors.sh

# 3. After all members complete — compute bred vectors and rescale
uv run python ../../spectre_utils/breed_vectors.py rescale ensemble/breed_config.yaml --cycle 1

# 4. Check convergence (per-variable RMS table)
uv run python ../../spectre_utils/breed_vectors.py status ensemble/breed_config.yaml --cycle 1

# 5. Repeat steps 2–4 for each cycle
#    Update --cycle 2, 3, ... 8
```

### GCP deployment

Each member directory (`member_001/` through `member_050/`) is self-contained:
- Perturbed pickup file (`.data` + `.meta`)
- `nIter0.txt` with the starting iteration

To run on GCP:
1. Copy the input deck and member pickups to each compute node's local disk
2. Each member runs standard MITgcm with the member's pickup as the restart file
3. After all members finish, copy pickups back and run the `rescale` step

## GCP Cost Estimate

### Cluster configuration

| Component | Machine type | Count | Purpose |
|-----------|-------------|-------|---------|
| Compute | h4d-standard-192 | 17 | 3 simulations per node (64 cores each) |
| Login | n1-standard-2 | 1 | SSH access, job submission |
| Controller | n1-standard-2 | 1 | Slurm controller |

### Compute requirements per cycle

- 50 members ÷ 3 per node = **17 nodes** per cycle
- 30 sim-days at 12–20 sim-days/wall-hr = **1.5–2.5 wall hours** per cycle
- 8 cycles × 2.5 hrs = **~20 hours** total wall time (plus ~30 min rescaling between cycles)
- Total compute: 17 nodes × 20 hrs = **340 node-hours** (conservative)

### Local disk per node

| Data | Size |
|------|------|
| EXF forcing (8 variables × 54 GB) | 432 GB |
| OBC boundary files | 20 GB |
| Grid, bathymetry, initial conditions | 2 GB |
| Pickup files (3 members) | 6 GB |
| Output headroom (diagnostics, pickups) | 40 GB |
| **Total** | **~500 GB** |

Recommend **1 TB pd-ssd** per compute node, or local NVMe SSD if available
on the machine type.

### Cost breakdown

| Item | On-demand | Spot (~70% discount) |
|------|-----------|---------------------|
| h4d-standard-192 × 340 node-hrs @ $9.64/hr | $3,278 | $983 |
| pd-ssd 1 TB × 17 nodes × 20 hrs @ $0.23/hr | $78 | $78 |
| n1-standard-2 × 2 × 24 hrs @ $0.095/hr | $5 | $5 |
| **Total** | **~$3,400** | **~$1,100** |

### Notes

- Spot/preemptible instances are viable since each breeding cycle is only
  1.5–2.5 hours — short enough to avoid most preemptions
- The 30-min rescaling step between cycles runs on a single node and is
  negligible cost
- Data transfer: ~500 GB input deck upload (one-time) + ~100 MB pickups per
  cycle (negligible)
- The control run must also advance 30 days per cycle to provide the reference
  state — this can run on one of the 17 compute nodes

## Configuration

All parameters are in `breed_config.yaml`:

```yaml
breeding:
  n_members: 50
  n_cycles: 8
  cycle_length_days: 30          # configurable
  target_amplitude:
    temperature_rms: 0.05        # °C
```

## Convergence monitoring

Run `breed_vectors.py status` after each cycle. You should see:

- **Cycles 1–3**: RMS ratios between variables shift as perturbations reorganize
- **Cycles 4–6**: Per-variable RMS stabilizes — bred vectors are converging
- **Cycles 7–8**: Minimal change — bred vectors have locked onto growing modes

If temperature RMS doesn't stabilize by cycle 8, increase `n_cycles` or
consider a shorter `cycle_length_days` to accelerate convergence.

## Directory structure

```
ensemble/
├── breed_config.yaml       # Breeding parameters
├── README.md               # This file
├── member_001/             # Member 1
│   ├── pickup.NNNNNNNNNN.data
│   ├── pickup.NNNNNNNNNN.meta
│   └── nIter0.txt
├── member_002/
│   └── ...
└── member_050/
    └── ...
```
