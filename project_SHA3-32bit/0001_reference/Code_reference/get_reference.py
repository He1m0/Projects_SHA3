import numpy as np
import os
from array import array
import sys
from pathlib import Path
import serv_manager as svm

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

import global_config as cfg

DIR = str(Path(__file__).resolve().parent)
folders = cfg.REFERENCE_FOLDERS
inputs = cfg.INPUTS
trace_len = cfg.REFERENCE_TRACE_LEN
invocations = cfg.INVOCATIONS

def read_wave(input_name):
  print(input_name)
  input_file = svm.Open(input_name, 'rb')
  float_array = array('d')
  float_array.frombytes(input_file.read())
  input_file.close()
  if len(float_array)==trace_len:
    return float_array
  else:
    print("Error: length.")
    exit()

def ref_calculate():
  total = np.array([0.0]*trace_len)
  for Set_n in range(0, folders):
    tag = "RE_"+str(Set_n).zfill(4)
    in_dir = DIR+"/Raw_"+tag+"/"
    in_zip = DIR+"/../Raw/Raw_"+tag+".zip"
    svm.System(("unzip "+in_zip))
    for t in range(0, inputs):
      for inv in range(0, invocations):
        print("=============================================================")
        InputName = in_dir+"trace_"+str(t).zfill(4)+"_"+str(inv)+"_ch0.bin"
        trace = read_wave(InputName)
        total += trace
    svm.System(("rm -vr "+in_dir))
  Average = total/(inputs*invocations*folders)
  svm.Save("ref_trace.npy", Average)


if __name__=='__main__':
  ref_calculate()
