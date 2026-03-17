# Spectre ensembles

This repository is adapted from https://github.com/quentinjamet/SPECTRE

Main differences include:
* MITgcm as a submodule
* Ocean boundary and initial conditions derived from Glorys v12
* Atmospheric forcing derived from ERA5, processed through the MITgcm EXF package
* All simulations are defined by a `config.yaml` that drives input deck generation and job submission


## Get Started

Clone this repository and recursively grab submodules:

```bash
git clone --recurse-submodules https://github.com/ocean-spectre/spectre-ensembles
cd spectre-ensembles
```


## Repository Layout

```
spectre-150-ensembles/
├── MITgcm/                  # MITgcm source (submodule)
├── env/                     # Environment setup scripts (per host)
├── opt/                     # MITgcm build option files (per host)
├── simulations/
│   └── glorysv12-curvilinear/   # Primary simulation (see its README)
│       ├── code/            # MITgcm compile-time options
│       ├── etc/config.yaml  # Simulation configuration
│       ├── input/           # Static input files and generated forcing
│       └── workflows/       # Slurm job scripts
└── spectre_utils/           # Python utilities for pre-processing
```


## Simulations

### glorysv12-curvilinear

MITgcm re-run of Glorys v12 on the native NEMO curvilinear grid for the North
Atlantic. See [`simulations/glorysv12-curvilinear/README.md`](simulations/glorysv12-curvilinear/README.md)
for the full workflow and configuration details.


## Claude Code Agents

This repository ships a set of Claude Code sub-agents in `.claude/agents/` that automate
common tasks when configuring and debugging MITgcm simulations. They are available
automatically whenever you open this project in Claude Code.

| Agent | When to use |
|-------|-------------|
| `mitgcm-stdout-diagnostics` | A run aborts or emits EXF/OBCS warnings — parses `STDOUT.*` across all MPI ranks, maps warnings to tile coordinates, and summarises the failure mode |
| `forcing-data-qc` | Suspect bad forcing data — checks EXF/OBC binary orientation, units, scale factors, and physical ranges against the source NetCDF and `data.exf` metadata |
| `namelist-validator` | Before submitting a run — cross-checks `data.exf`, `data.obcs`, and `data` for grid dimension consistency, start dates, file periods, and missing files |
| `workflow-runner` | Submit or monitor a SLURM workflow job, tail logs, and retrieve a completion summary |
| `model-output-review` | After a short test run — reads MNC tile output, computes summary statistics for key fields (SST, SSH, velocities), and flags signs of numerical instability |
| `web-research` | Look up MITgcm source code or documentation, ERA5 variable conventions, SLURM flags, or any other technical reference on the internet |

### Example usage

```
# Diagnose why a run failed at it=0
Use the mitgcm-stdout-diagnostics agent on simulations/glorysv12-curvilinear/new/

# Validate forcing files before re-running
Use the forcing-data-qc agent to check all EXF binaries in input/

# Look up a MITgcm namelist parameter
Use the web-research agent to find what exf_scal_BulkCdn does in data.exf
```


## spectre_utils

Python package containing all pre-processing scripts. All scripts accept a
`config.yaml` path as their only argument. Key scripts:

| Script | Purpose |
|--------|---------|
| `download_glorys12_raw.py` | Download Glorys v12 ocean data from CMEMS |
| `download_era5.py` | Download ERA5 atmospheric data from CDS |
| `mk_initial_conditions.py` | Generate MITgcm initial conditions |
| `mk_ocean_boundary_conditions.py` | Generate open boundary conditions |
| `mk_exf_conditions.py` | Process ERA5 fields into EXF binary forcing files |
| `animate_exf_conditions.py` | Animate EXF forcing fields (MP4 per variable) |
| `review_exf_conditions.py` | QC checks, statistics, and diagnostic figures |
