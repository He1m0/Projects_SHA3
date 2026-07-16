import numpy as np
import h5py
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve()
while not (ROOT_DIR / "global_config.py").exists() and ROOT_DIR != ROOT_DIR.parent:
  ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))

import global_config as cfg

ICS_WINDOW = cfg.TRAINING_ICS_WINDOW
PART_COUNT = cfg.TRAINING_PART_COUNT
ICS_LEVEL = str(cfg.TRAINING_ICS_LEVEL).zfill(3)

ICS_DIR = 'ics_original_'+ICS_LEVEL+'/'

class IOPS_Extractor:
  def __init__(self):
    self.CompleteTraceFiles = []
    for t in range(0, PART_COUNT):
      fname = '../Processed_HDF5/part_'+str(t).zfill(2)+'.hdf5'
      print('Loading', fname)
      self.CompleteTraceFiles.append(h5py.File(fname, 'r'))
    return
  
  def close(self):
    for t in range(0, PART_COUNT):
      print('Closing file part '+str(t).zfill(2))
      self.CompleteTraceFiles[t].close()
  
  def get_IoPs(self, Tag, Num):
    name_output = 'IoPs/Ints_'+Tag+'_i'+str(Num).zfill(2)+'.hdf5'
    if os.path.exists(name_output):
      print(Tag+' i'+str(Num).zfill(2), 'already exists, skipping')
      return
    print('=====================================================')
    print(Tag+' i'+str(Num).zfill(2))
    name_ics = ICS_DIR+'ics_'+Tag+'_i'+str(Num).zfill(2)+'.npy'
    ICs = np.load(name_ics)
    cols = np.concatenate([
        np.arange(int(ICs[it]) * ICS_WINDOW, int(ICs[it]) * ICS_WINDOW + ICS_WINDOW)
        for it in range(len(ICs))
    ])
    unique_cols, inverse = np.unique(cols, return_inverse=True)
    IoPs = []
    for part in range(0, PART_COUNT):
      print('part '+str(part).zfill(2), time.asctime())
      data_unique = self.CompleteTraceFiles[part]['Traces'][:, unique_cols]
      IoPs.append(data_unique[:, inverse])
    # Write to a temp name and rename into place atomically -- if this
    # process is killed mid-write, no partial/truncated file is left
    # behind under the final name, so the exists-check above can't be
    # fooled into skipping a corrupt output on a later resume.
    tmp_output = name_output + '.tmp'
    FILE = h5py.File(tmp_output, 'w')
    FILE.create_dataset('IoPs', compression="gzip", compression_opts=9, data=np.vstack(IoPs))
    FILE.close()
    os.replace(tmp_output, name_output)
  
  def get_state(self, tag, lower, upper):
    for ints in range(lower, upper):
      self.get_IoPs(tag, ints)
    return
  
  def get_round(self, RD):
    self.get_state('A'+str(RD).zfill(2), 0, 50)
    self.get_state('B'+str(RD).zfill(2), 0, 50)
    self.get_state('C'+str(RD).zfill(2), 0, 10)
    self.get_state('D'+str(RD).zfill(2), 0, 10)
    return
    
if __name__=='__main__':
  rd = int(sys.argv[1])
  Extractor = IOPS_Extractor()
  Extractor.get_round(rd)
  Extractor.close()
