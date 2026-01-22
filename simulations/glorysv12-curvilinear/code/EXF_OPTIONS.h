CBOP
C !ROUTINE: EXF_OPTIONS.h
C !INTERFACE:
C #include "EXF_OPTIONS.h"

C !DESCRIPTION:
C *==================================================================*
C | CPP options file for EXternal Forcing (EXF) package:
C | Control which optional features to compile in this package code.
C *==================================================================*
CEOP

#ifndef EXF_OPTIONS_H
#define EXF_OPTIONS_H
#include "PACKAGES_CONFIG.h"
#include "CPP_OPTIONS.h"

#ifdef ALLOW_EXF


C ** Bulk formula options ** 
C compute hs/hl/evap etc via bulk formulae
#define ALLOW_BULKFORMULAE 
C Large & Yeager (2004) mods to bulk formulae
#define ALLOW_BULK_LARGEYEAGER04
C Large & Yeager (2009) drag coeff behaviour
#define ALLOW_DRAG_LARGEYEAGER09 

C  read uwind/vwind, compute stress
#define ALLOW_ATM_WIND           
C read atemp/aqh and compute buoyancy/turb fluxes 
#define ALLOW_ATM_TEMP           
C read swdown/lwdown and compute net fluxes
#define ALLOW_DOWNWARD_RADIATION 
C read runoff from file
#define ALLOW_RUNOFF
C read evaporation from file
#define EXF_READ_EVAP


C ** Interpolation / Vector rotation behavior ** 
#define USE_EXF_INTERPOLATION
#define EXF_INTERP_USE_DYNALLOC

#endif
