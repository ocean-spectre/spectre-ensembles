#!/bin/bash

export spectre_ensembles="/group/tdgs/joe/spectre-150-ensembles"

###############################################################################################
#   Setup the software environment
###############################################################################################


# Set up conda
__conda_setup="$('$HOME/miniconda3/bin/conda' 'shell.bash' 'hook' 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__conda_setup"
else
    if [ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]; then
        . "$HOME/miniconda3/etc/profile.d/conda.sh"
    else
        export PATH="$HOME/miniconda3/bin:$PATH"
    fi
fi
unset __conda_setup

# Check if environment already exists
if conda env list | grep -q "spectre"; then
    echo "Environment 'spectre' already exists. Activating it."
    conda activate spectre
else
    echo "Creating environment 'spectre'."
    conda create -n spectre python=3.10 --yes
    conda activate spectre
    pip install -r requirements.txt
fi

module load ffmpeg
