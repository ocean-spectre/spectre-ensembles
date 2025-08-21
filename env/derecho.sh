export spectre_cwd=$(pwd)
export spectre_optfile="${spectre_cwd}/opt/derecho"
export spectre_simulation_template='mitgcm50_z75' #TODO: Set your simulation template here!
export spectre_rank_count=192
export spectre_ensemble_root='simulations'
export dirModel="${spectre_cwd}/MITgcm"

module --force purge
module load ncarenv/24.12 intel-oneapi/2024.2.1 cray-mpich/8.1.29 hdf5/1.12.3 netcdf/4.9.2 


