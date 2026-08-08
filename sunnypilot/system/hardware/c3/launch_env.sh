#!/usr/bin/env bash

export OMP_NUM_THREADS=1
export MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1
export OPENBLAS_NUM_THREADS=1
export VECLIB_MAXIMUM_THREADS=1

if [ -z "$AGNOS_VERSION" ]; then
  # Match current C3 /VERSION (12.8). Mismatch triggers full AGNOS reflash on launch.
  export AGNOS_VERSION="12.8"
fi

export STAGING_ROOT="/data/safe_staging"
