# Spectre - 150

This repository is adapted from https://github.com/quentinjamet/SPECTRE

Main differences include
* MITgcm as a submodule
* Ocean boundary conditions are from Glorys v12 and the same across all ensemble members


## Get Started
Clone this repository and recursively grab submodules

```
git clone --recurse-submodules https://github.com/ocean-spectre/spectre-150
```


## Workflow

Set up template directory (manual work)
|
|
build mitgcm executable
|
|
Define ensemble configurations with simulation sequences
|
|
Create boundary and atm conditions (constant across all members)
|
|
Set up member directories
|
|
Create initial conditions (unique for each member)
|
|
For each member, launch simulation sequences


### What's a simulation sequence ?

Defined by
* sequence stage - a name for this "stage" of the simulation (e.g. spinup, production)
* map of MITgcm parameters to their values
* list of required conditions to start
* list of conditions to verify successful completion 
