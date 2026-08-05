#!/usr/bin/env bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

if [ -z "$AGNOS_VERSION" ]; then
  # Match office C3 /VERSION (12.6). 12.8 triggers full AGNOS reflash on launch.
  export AGNOS_VERSION="12.6"
fi

export STAGING_ROOT="/data/safe_staging"
