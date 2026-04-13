import numpy as np
import SASCA_iteration_scan
import serv_manager as svm
import os
import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve()
while not (ROOT_DIR / "global_config.py").exists() and ROOT_DIR != ROOT_DIR.parent:
  ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))
import global_config as gc

###################################################################################
# Independent parameters
# Rounds:
ROUND = 2
Dir_Table = 'Bit_Tables/'
ALLOWED_WRONG_BITS = gc.SASCA_ALLOWED_WRONG_BITS
###################################################################################

def loopy_BP_scan(tr):
  print('======================================================')
  print('Trace: '+str(tr).zfill(4)+' '+time.asctime())
  #print('Table loading...')
  b_ALL = svm.Load((Dir_Table+'Tables_INP/table_'+str(tr).zfill(4)+'.npy'))
  b_C = []
  b_D = []
  b_A = []
  b_B = []
  for rd in range(0, ROUND):
    b_C.append(svm.Load((Dir_Table+'Tables_C'+str(rd).zfill(2)+'/table_'+str(tr).zfill(4)+'.npy')))
    b_D.append(svm.Load((Dir_Table+'Tables_D'+str(rd).zfill(2)+'/table_'+str(tr).zfill(4)+'.npy')))
    b_A.append(svm.Load((Dir_Table+'Tables_A'+str(rd).zfill(2)+'/table_'+str(tr).zfill(4)+'.npy')))
    b_B.append(svm.Load((Dir_Table+'Tables_B'+str(rd).zfill(2)+'/table_'+str(tr).zfill(4)+'.npy')))
  #print('Loading answer...')
  answer = svm.Load('answer_bit/answers_A00/ans_bit_'+str(tr).zfill(4)+'.npy')
  #print('Loopy-BP processing...')
  #print('  ================================================')
  rate = gc.SASCA_KNOWN_RATE_BITS
  b_INP = np.hstack([0.5*np.ones((2, rate)), b_ALL[:,rate:]])
  Predictions = SASCA_iteration_scan.State_Scan(ROUND, b_INP, np.array(b_C), np.array(b_D), np.array(b_A), np.array(b_B))
  wrong_bits = np.count_nonzero(Predictions!=answer, axis=1)
  Success = (wrong_bits<=ALLOWED_WRONG_BITS)
  print('Trace {} summary: best_wrong_bits={}, final_wrong_bits={}, success_count={}/{}'.format(
    str(tr).zfill(4), int(np.min(wrong_bits)), int(wrong_bits[-1]), int(np.count_nonzero(Success)), len(Success)
  ))
  print('Saving results')
  svm.Save(('Success/success_'+str(tr).zfill(4)+'.npy'), Success)
  return

if __name__=='__main__':
  L = int(sys.argv[1])
  U = int(sys.argv[2])
  tS = time.time()
  for t in range(L, U):
    loopy_BP_scan(t)
  print('++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++++')
  tE = time.time()
  print('Finished!')
  print('Exec. Time:', (tE-tS))


