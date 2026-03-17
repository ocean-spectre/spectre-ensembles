# CLAUDE.md — spectre-ensembles

Context for Claude Code when working in this repository.

## What this project is

MITgcm realistic ocean simulation of the North Atlantic (26–54°N), driven by:
- **Initial / boundary conditions**: Glorys v12 daily fields from CMEMS (T, S, U, V, SSH)
- **Atmospheric forcing**: ERA5 3-hourly single-level fields via the MITgcm EXF package
- **Grid**: Native NEMO curvilinear grid, 768 × 424 × 50 levels, MPI 8×8 = 64 ranks

Primary simulation: `simulations/glorysv12-curvilinear/`


## Repository layout

```
spectre-150-ensembles/
├── .claude/agents/          # Claude Code sub-agent definitions
├── MITgcm/                  # MITgcm source (git submodule)
├── opt/                     # MITgcm build option files (per host)
├── simulations/
│   └── glorysv12-curvilinear/
│       ├── code/            # Compile-time CPP options (SIZE.h, packages.conf, etc.)
│       ├── etc/config.yaml  # Single source of truth for all workflow parameters
│       ├── input/           # Binary forcing files and static grid files
│       ├── downloads/       # Raw NetCDF downloads (ERA5, GLORYS)
│       ├── new/             # Most recent MITgcm run output (MNC NetCDF tiles)
│       └── workflows/       # Slurm job scripts (source env.sh for paths/images)
└── spectre_utils/           # Python pre-processing package (run inside container)
```


## Infrastructure

- **Cluster**: Spectre (Franklin) — SLURM scheduler, BeeGFS parallel filesystem
- **Containers**: All Python workflows and MITgcm run inside Docker containers via enroot+pyxis
- **Container images** (defined in `workflows/env.sh`):
  - `SPECTRE_UTILS_IMG` — Python pre-processing (spectre_utils package)
  - `MITGCM_BASE_IMG` — MITgcm MPI executable
- **Image rebuild**: Changes to `spectre_utils/` require a commit+push to trigger the GitHub Actions image build before the new code is available in SLURM jobs
- **sbatch working directory**: Always pass `--chdir=.../simulations/glorysv12-curvilinear` so relative paths in scripts resolve correctly


## Critical conventions and known gotchas

### EXF binary latitude orientation
ERA5 NetCDF stores latitude **north-to-south** (j=0 = 60°N). MITgcm `data.exf` uses `lat0=20.0, lat_inc=+0.25`, which expects the binary to be **south-to-north** (j=0 = 20°N). The code in `mk_exf_conditions.py` must flip the latitude axis before writing:
```python
ds = ds.isel(latitude=slice(None, None, -1))
```
Failing to flip causes MITgcm EXF to read ~54°N data when interpolating to model grid points at ~26°N, creating a ~20°C air-sea temperature error and triggering EXF range-check failures at it=0.

### EXF range-check thresholds (hardcoded in `exf_check_range.F`)
- `hflux`: fails if > +1600 or < -500 W/m² (not ±2000 as the default comments imply)
- `ustress` / `vstress`: fails if > ±2.0 N/m²

### MITgcm bulk formula
The code is compiled with `ALLOW_BULK_LARGEYEAGER04`. MITgcm uses the **Large & Yeager (2009)** stability-corrected bulk formula, not simple constant-coefficient formulas. Drag coefficients are wind-speed-dependent: `Cd = cDrag_1/|U| + cDrag_2 + cDrag_3*|U| + cDrag_8*|U|^6`, with `niter_bulk=2` stability iterations. Simplified diagnostic scripts (e.g. `compute_bulk_fluxes.py`) will underestimate flux magnitudes.

### MNC tile numbering
MNC output directory `mnc_<timestamp>_NNNN/` contains output for **PID = NNNN − 1**. PID 0 is in directory `mnc_*_0001/` and writes tile `t004` (not `t001`). Always locate the grid file per directory rather than assuming PID↔tile ordering.

### ERA5 scale factors for accumulated variables
ERA5 accumulated fields (swdown, lwdown, precip, evap, runoff) are in J/m² or m per accumulation period. The correct scale factor to convert 3-hourly accumulations to W/m² or m/s is `1/10800 = 9.2593e-5`. The config currently uses `2.7778e-4 = 1/3600` (hourly rate) — this is a known discrepancy to be revisited.

### MITgcm EXF does not support negative `lat_inc`
The `exf_interp.F` binary search assumes monotonically increasing latitude. Do not attempt to fix the orientation mismatch by setting `lat_inc = -0.25` in `data.exf` — it will silently produce wrong results.

### OBC vs EXF periods
- EXF atmospheric forcing: 3-hourly → `period = 10800.0` seconds
- OBC ocean boundaries: daily → `period = 86400.0` seconds


## Workflow sequence

1. `download_era5.sh` — download ERA5 NetCDF per variable per year into `downloads/`
2. `make_exf_conditions.sh` — convert ERA5 NetCDF → EXF binary in `input/` (requires up-to-date Docker image)
3. `run.sh` — launch MITgcm; output goes to `new/` (MNC NetCDF tiles) and `new/STDOUT.*`


## Python environment

Scripts are run inside the container. For local development/debugging:
```bash
uv run python spectre_utils/<script>.py simulations/glorysv12-curvilinear/etc/config.yaml
```
Dependencies are managed with `uv` (`pyproject.toml` / `uv.lock`).
