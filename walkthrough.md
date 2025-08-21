# MITgcm on derecho

## Introduction
Below is an tree of this repository that has been used to run a few simulations. I.e., it captures the repo (mainly `/simulations`) "mid-use".

repo: https://github.com/ocean-spectre/spectre-ensembles
```
spectre-150
    ├── build
    ├── exe                 <-- build dir for MITgcm
    ├── MITgcm              <-- submodule for MITgcm
    ├── opt                 <-- define build options in files under opt
    ├── simulations         <-- where do define parameters for your simulation
    │   ├── mitgcm50_z75            <-- simulation name
    │   │   ├── 192                 <-- MPI ranks
    │   │   │   └── code            <-- comes with repo, used to configure run (/templates/code)
    │   │   ├── 384
    │   │   │   ├── code
    │   │   │   ├── testrun         <-- job output directory
    │   │   │   └── testrun_6node
    │   │   ├── 768
    │   │   │   ├── code
    │   │   │   └── testrun
    │   │   └── input
    │   └── mitgcm50_z75_annual
    │       └── code
    └── src
```

## Steps to run MITgcm

### download the repo
```bash
git clone --recurse-submodules https://github.com/ocean-spectre/spectre-ensembles
cd spectre-ensembles
```

### set up simulations/templates
This repo comes with a pre-configured simulation at `simulations/mitgcm50_z75`.
The directory structure goes: `simulations/<simulation name>/<mpi ranks>`. Within `simulations/<simulation name>/<mpi ranks>/code`, you'll find `SIZE.h`, where you can define the size (i.e., number of points/tiles/processes for each dimension) for your simulation. Below are the relevant lines (lines 45-55).
```c
     &           sNx =  40,
     &           sNy =  83,
     &           OLx =   3,
     &           OLy =   3,
     &           nSx =   1,
     &           nSy =   1,
     &           nPx =   32,
     &           nPy =   12,
     &           Nx  = sNx*nSx*nPx,
     &           Ny  = sNy*nSy*nPy,
     &           Nr  =   75)
```

### build mitgcm
set rank count (line 6)
```bash
./workflows/build-mitgcm.sh -e env/derecho.sh
```


### preparing testrun script
in `testrun384.sh`:
- set required resources in PBS header (line 9)
```bash
#PBS -l select=6:ncpus=64:mpiprocs=64:mem=196GB
```
- set your simulation template
```bash
simulation_template='mitgcm50_z75' #TODO: Set your simulation template here!
```
- set mpiranks (line 21)
```bash
rank_count=384
```
- set `nranks_per_node` (line 26)
```bash
nranks_per_node=64
```
- set `rundir` (line 23)
```bash
rundir='testrun_6node' # can be set to member id
```


### submitting a job
```bash
qsub testrun384.sh
qstat -u gbyrd
```
### Checking output files
every timestep outputs `<variable>.<timestep>.data` and `<variable>.<timestep>.meta`.

(variables : S,T,U,V,W,Eta,PH,PHL; timestep : 10 digit integer)

e.g., `W.0000000000.data`

outputs land at `simulations/<simulation_template>/<rank_count>/<rundir>`, e.g.,
```bash
simulations/mitgcm50_z75/384/testrun_6node/
```

### checking on jobs
```bash
qstat -u gbyrd
qstat -x -u gbyrd   <-- -x flag used to show jobs that have recently finished
```
stderr and stdout files will output in directory job was launched

```bash
gbyrd@derecho6:/glade/work/gbyrd/test> qstat -u gbyrd

desched1:
                                                            Req'd  Req'd   Elap
Job ID          Username Queue    Jobname    SessID NDS TSK Memory Time  S Time
--------------- -------- -------- ---------- ------ --- --- ------ ----- - -----
2454164.desche* gbyrd    cpu      memb00        --    1   1    1gb 00:00 Q   --

gbyrd@derecho6:/glade/work/gbyrd/test> ls
memb00.e2454164  memb00.o2454164  test.sh
```


## Misc
A cool resource for `PBS` vs Slurm commands:

https://oit.utk.edu/hpsc/isaac-open-enclave-new-kpb/isaac-open-enclave-slurm/


