import numpy as np
import os
import Template_validate_LDA as template
import serv_manager as svm
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve()
while not (ROOT_DIR / "global_config.py").exists() and ROOT_DIR != ROOT_DIR.parent:
  ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

import global_config as cfg

L = int(sys.argv[1])
U = int(sys.argv[2])
for tSet in range(L, U):
  lower = tSet*cfg.VALIDATION_SETS_PER_PART
  upper = min(lower+cfg.VALIDATION_SETS_PER_PART, cfg.VALIDATION_SET_COUNT)
  trace_count = (upper-lower)*cfg.VALIDATION_INPUTS*cfg.INVOCATIONS
  if trace_count<=0:
    continue
  template.main(tSet, trace_count)
  print("++++++++++++++++++++++++++++++++++++++++++++++++++")
