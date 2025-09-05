export spectre_cwd=$(pwd) # The local full path to the spectre-ensembles repository
export spectre_optfile="${spectre_cwd}/opt/derecho" # The opt file you want to use to build with
export spectre_mitgcm_source_code="${spectre_cwd}/MITgcm" # The path the the MITgcm source code
export spectre_model_code=$spectre_cwd/simulations/mitgcm50_z75/192/code # The `code/` directory with MITgcm customizations and build time parameters
export spectre_model_input=$spectre_cwd/simulations/mitgcm50_z75/192/code # Where your model input deck comes from
export spectre_model_exe_dir=$spectre_cwd/exe # Where you will run the MITgcm


module --force purge
module load ncarenv/24.12 intel-oneapi/2024.2.1 cray-mpich/8.1.29 hdf5/1.12.3 netcdf/4.9.2 


