export spectre_cwd=$(pwd) # The local full path to the spectre-ensembles repository
export spectre_optfile="${spectre_cwd}/opt/galapagos-franklin" # The opt file you want to use to build with
export spectre_mitgcm_source_code="${spectre_cwd}/MITgcm" # The path the the MITgcm source code
export spectre_model_code=$spectre_cwd/simulations/mitgcm50_z75/192/code # The `code/` directory with MITgcm customizations and build time parameters
export spectre_model_input=$spectre_cwd/simulations/mitgcm50_z75/192/code # Where your model input deck comes from
export spectre_model_exe_dir=$spectre_cwd/exe # Where you will run the MITgcm


module --force purge
module load gcc/13.4.0
module load openmpi/5.0.8
module load netcdf-c/4.9.3
module load netcdf-fortran/4.6.2

export NETCDF_ROOT=$NETCDF_FORTRAN_ROOT
export LD_LIBRARY_PATH=$NETCDF_ROOT/lib:$NETCDF_FORTRAN_ROOT/lib:$LD_LIBRARY_PATH