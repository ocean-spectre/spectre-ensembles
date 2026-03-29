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

This repository ships Claude Code sub-agents in `.claude/agents/` that automate
MITgcm simulation operations. They follow a clear division of labor:

### Orchestrator (decision-maker)

| Agent | Role |
|-------|------|
| `simulation-orchestrator` | Manages the full run-diagnose-fix-rerun lifecycle. Coordinates sub-agents, makes configuration decisions (timestep, output, nodes), manages infrastructure (dashboard, plotter, tailscale). This is the primary agent. |

### Specialists (report to orchestrator)

| Agent | Role | Outputs |
|-------|------|---------|
| `namelist-validator` | Pre-flight check before submitting a run | PASS/FAIL report per check |
| `mitgcm-stdout-diagnostics` | Post-mortem when a run fails | Structured failure diagnosis with suggested fix |
| `model-output-review` | Health check after a successful run segment | Physical plausibility assessment |
| `forcing-data-qc` | Validate forcing binary files | Per-file QC report |

### Infrastructure

| Agent | Role |
|-------|------|
| `workflow-runner` | Submit SLURM jobs, start/stop background processes. Execution only — hands failures to diagnostics agents |
| `dashboard-manager` | Health-check and restart the dashboard/converter/plotter stack |
| `notify` | Send Slack messages (#mitgcm-ocean) or email (fallback) to the user. Used by the orchestrator to request decisions or report milestones |
| `web-research` | Look up MITgcm docs, ERA5 conventions, SLURM flags | Internet research only |

### Workflow

```
                    ┌─────────────────────┐
                    │    orchestrator      │
                    │  (decision-maker)    │
                    └──────┬──────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼─────┐   ┌─────▼─────┐   ┌─────▼─────┐
    │  validate  │   │    run    │   │  diagnose  │
    │ namelists  │   │  submit   │   │  failure   │
    └────────────┘   └─────┬─────┘   └────────────┘
                           │
                    ┌──────▼──────┐
                    │   monitor   │
                    │  dashboard  │
                    └─────────────┘
```

1. **Before run**: orchestrator delegates to `namelist-validator`
2. **Submit**: orchestrator delegates to `workflow-runner`
3. **Monitor**: dashboard runs continuously
4. **On failure**: orchestrator delegates to `mitgcm-stdout-diagnostics`
5. **On success**: orchestrator delegates to `model-output-review`
6. **Research**: any agent can delegate to `web-research`


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
