import numpy as np
import sys
from pathlib import Path
import KECCAK as kec

ROOT_DIR = Path(__file__).resolve()
while not (ROOT_DIR / "global_config.py").exists() and ROOT_DIR != ROOT_DIR.parent:
  ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

import global_config as cfg

SET_COUNT = cfg.TRAINING_SET_COUNT
INPUTS = cfg.INPUTS
INVOCATIONS = cfg.INVOCATIONS

def state_to_hex(state):
  hex_str = ""
  for lane in range(0, 25):
    temp = state[lane]
    for b in range(0, 8):
      byte = temp&0xff
      hex_str += (hex(byte)[2:]).zfill(2)
      temp = temp>>8
  return hex_str

def keccak_10(M):
  Str_in =[]
  Str_out =[]
  N = kec.padding_SHA3(M, 576)
  Lanes = kec.hex2lane(N)
  State = [0]*25
  for t in range(0, INVOCATIONS):
    for L in range(0, 9):
      State[L] ^= Lanes[(t*9+L)]
    in_str = state_to_hex(State)
    State = kec.Keccak_f1600(State)
    out_str = state_to_hex(State)
    Str_in.append(in_str)
    Str_out.append(out_str)
  return Str_in, Str_out

def find_IO():
  all_input = []
  all_output = []
  short_input = []
  short_output = []
  for set_n in range(0, SET_COUNT):
    print("Loading files of set #"+str(set_n))
    infile = np.load(("data_raw_in/Raw_TR_"+str(set_n).zfill(4)+"_data_in.npy"))
    outfile = np.load(("data_raw_out/Raw_TR_"+str(set_n).zfill(4)+"_data_out.npy"))
    for t in range(0, INPUTS):
      short_input.append(infile[t])
      short_output.append(outfile[t])
  for x in range(0, SET_COUNT*INPUTS):
    print("Executing sponge #"+str(x))
    Inter_In, Inter_Out = keccak_10(short_input[x])
    temp = Inter_Out[INVOCATIONS-1]
    if temp[0:128]!=short_output[x]:
      print("Error: outputs not match.")
      return
    for invoc in range(0, INVOCATIONS):
      all_input.append(Inter_In[invoc])
      all_output.append(Inter_Out[invoc])
  np.save("Invocation_IO/trace_input.npy", all_input)
  np.save("Invocation_IO/trace_output.npy", all_output)
  return

def checking():
  Error_Index = []
  In = np.load("Invocation_IO/trace_input.npy")
  Out = np.load("Invocation_IO/trace_output.npy")
  for t in range(0, SET_COUNT*INPUTS*INVOCATIONS):
    print("=================================================")
    print("Checking trace #"+str(t))
    Lanes = kec.hex2lane(In[t])
    State = kec.Keccak_f1600(Lanes)
    Out_str = state_to_hex(State)
    if Out_str==Out[t]:
      print("Passed!")
    else:
      print("Falied!")
      Error_Index.append(t)
  if np.size(Error_Index)==0:
    return "ALL PASSED!"
  return Error_Index

if __name__=='__main__':
  tag = sys.argv[1]
  if tag=="cal":
    find_IO()
  if tag=="check":
    print(checking())







