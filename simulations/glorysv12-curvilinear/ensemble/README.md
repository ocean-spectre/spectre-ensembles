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

Each member has its own set of initial condition files (`T.init.bin`,
`S.init.bin`, `U.init.bin`, `V.init.bin`, `Eta.init.bin`). The cycle operates
on these IC files directly:

```
Control ICs:  T.init.bin, S.init.bin, U.init.bin, V.init.bin, Eta.init.bin
                 │
                 │  add perturbation (breed_vectors.py init)
                 ▼
Member ICs:   T.init.bin, S.init.bin, ... (in member_NNN/)
                 │
                 │  run MITgcm from nIter0=0 for 30 days
                 ▼
Member pickup at t=30 days (pickup.0000007200.data)
                 │
                 │  bred_vector = member_pickup - control_pickup
                 │  rescale by target_RMS / actual_T_RMS
                 │  new_IC = control_IC + rescaled_bred_vector
                 ▼
Member ICs:   overwritten with new perturbation → next cycle
```

Key points:
- Every cycle starts from **nIter0=0** — the member's IC files are the
  perturbation mechanism, not pickup files
- The **same forcing, grid, and namelist files** are shared across all members
  (symlinked from the master input directory). Only the IC files differ.
- Bred vectors are computed from the **pickup at t=30 days**, which captures
  how the perturbation grew over the cycle
- The **same rescale factor** (derived from temperature RMS) is applied to
  all variables to preserve dynamical balance
- For **production runs** after breeding converges, each member restarts from
  its pickup at t=30 days (iteration 7200)

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

### Time-varying forcing during breeding

Breeding is performed under the full time-varying atmospheric (ERA5) and ocean
boundary (GLORYS) forcing — not frozen or climatological forcing. This is the
correct approach for two reasons:

1. **Bred vectors should capture the growing modes of the actual system
   trajectory.** The fastest-growing instabilities in the North Atlantic depend
   on the seasonal forcing state — Gulf Stream separation behavior differs
   between winter and summer, deep convection only occurs in winter, and summer
   stratification modulates baroclinic instability. Breeding under realistic
   forcing ensures the perturbations project onto modes that are actually
   growing in the flow regime the ensemble will simulate.

2. **The forcing cancels in the bred vector computation.** Both the control and
   perturbed members see identical forcing. The bred vector (`member − control`)
   isolates perturbation growth only — the common forcing signal drops out.
   Time-varying forcing drives the background state but does not contaminate
   the perturbation structure.

If breeding were performed under constant (frozen) forcing, the perturbations
would lock onto modes specific to that frozen state and need time to readjust
when exposed to evolving forcing in the production ensemble — partially
defeating the purpose of breeding.

**Seasonal timing**: Ideally, start breeding from the same season as the
production ensemble start date, so the bred vectors are tuned to the relevant
flow regime. For multi-year ensembles this is a minor consideration — bred
vectors readjust within the first few weeks of the production run regardless.

## Workflow

### Prerequisites

- Completed control spinup run (1 year)
- Control run must also be run from nIter0=0 for 30 days (same as members)
  to produce the reference pickup for bred vector computation

### Steps

```bash
cd simulations/glorysv12-curvilinear

# 1. Initialize 50 perturbed IC files from the control ICs
uv run python ../../spectre_utils/breed_vectors.py init ensemble/breed_config.yaml

# 2. Run all 50 members for one 30-day cycle (SLURM array job)
#    Each member starts from nIter0=0 with its perturbed ICs
sbatch --chdir=$(pwd) workflows/breed_vectors.sh

# 3. After all members complete — compute bred vectors and overwrite ICs
uv run python ../../spectre_utils/breed_vectors.py rescale ensemble/breed_config.yaml --cycle 1

# 4. Check convergence (per-variable RMS table)
uv run python ../../spectre_utils/breed_vectors.py status ensemble/breed_config.yaml

# 5. Repeat steps 2–4 for each cycle (2, 3, ... 8)
```

### Running the control alongside members

The control must also produce a pickup at iteration 7200 (30 days from nIter0=0)
for the bred vector computation. This can be done:
- As a separate single run with the same `data` settings as the members
- On one of the 17 compute nodes alongside 2 members (3 sims per node)

### Transitioning to production

After breeding converges (cycle 5–8):
1. Each member has a pickup at `member_NNN/run/pickup.0000007200.data`
2. Copy this pickup to the member's production run directory
3. Set `nIter0=7200` and full production `endTime`/`nTimeSteps`
4. Run the production ensemble

## GCP deployment

Each member directory (`member_001/` through `member_050/`) contains:
- `T.init.bin`, `S.init.bin`, `U.init.bin`, `V.init.bin`, `Eta.init.bin`

To run on GCP:
1. Copy the master input deck to each compute node's local disk (one copy per node)
2. Copy each member's IC files to the node
3. Set up the member run directory: symlink master input, replace IC symlinks with copies
4. Run MITgcm with `nIter0=0`, `nTimeSteps=7200`
5. After all members finish, copy pickups back and run the `rescale` step

### Cluster configuration

| Component | Machine type | Count | Purpose |
|-----------|-------------|-------|---------|
| Compute | h4d-standard-192 | 17 | 3 simulations per node (64 cores each) |
| Login | n1-standard-2 | 1 | SSH access, job submission |
| Controller | n1-standard-2 | 1 | Slurm controller |

### Cost estimate

| Item | On-demand | Spot (~70% discount) |
|------|-----------|---------------------|
| h4d-standard-192 × 340 node-hrs @ $9.64/hr | $3,278 | $983 |
| pd-ssd 1 TB × 17 nodes × 20 hrs @ $0.23/hr | $78 | $78 |
| n1-standard-2 × 2 × 24 hrs @ $0.095/hr | $5 | $5 |
| **Total** | **~$3,400** | **~$1,100** |

### Local disk per node

| Data | Size |
|------|------|
| EXF forcing (8 variables × 54 GB) | 432 GB |
| OBC boundary files | 20 GB |
| Grid, bathymetry, other input | 5 GB |
| Member IC files (3 members × 5 files × 130 MB) | 2 GB |
| Output headroom (pickups) | 40 GB |
| **Total** | **~500 GB** |

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
├── convergence.json        # Per-cycle RMS diagnostics (written by rescale)
├── README.md               # This file
├── member_001/             # Member 1
│   ├── T.init.bin          # Perturbed temperature IC
│   ├── S.init.bin          # Perturbed salinity IC
│   ├── U.init.bin          # Perturbed zonal velocity IC
│   ├── V.init.bin          # Perturbed meridional velocity IC
│   ├── Eta.init.bin        # Perturbed SSH IC
│   └── run/                # MITgcm run directory (created by breed_vectors.sh)
│       ├── *.bin → /input/ # Symlinks to master input (forcing, grid, OBC)
│       ├── T.init.bin      # Copied (not symlinked) from member dir
│       ├── data            # Member-specific (nIter0=0, nTimeSteps=7200)
│       └── pickup.0000007200.data  # Output: state at t=30 days
├── member_002/
│   └── ...
└── member_050/
    └── ...
```
