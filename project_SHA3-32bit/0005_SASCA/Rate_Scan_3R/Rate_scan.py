import numpy as np
import SASCA_scan
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
ROUND = 3
Dir_Table = 'Bit_Tables/'
ALLOWED_WRONG_BITS = gc.SASCA_ALLOWED_WRONG_BITS
RATE_POINT_COUNT = gc.SASCA_RATE_POINT_COUNT
RATE_STEP_BITS = gc.SASCA_RATE_STEP_BITS
###################################################################################

def get_prediction(Table):
  State = []
  for bit in range(0, 1600):
    if Table[0][bit]>0.5:
      State.append(0)
    else:
      State.append(1)
  return np.array(State)

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
  answer_len = int(answer.shape[0])
  #print('Loopy-BP processing...')
  Results = []
  best_wrong_bits = answer_len
  best_point = 0
  best_unknown_bits = 0
  baseline_wrong_bits = answer_len
  final_wrong_bits = answer_len
  final_unknown_wrong = answer_len
  final_known_wrong = answer_len
  final_unknown_bits = 0
  for byte in range(0, RATE_POINT_COUNT):
    #print('  ================================================')
    unknown_bits = min(byte*RATE_STEP_BITS, answer_len)
    b_INP = np.hstack([0.5*np.ones((2, unknown_bits)), b_ALL[:,unknown_bits:]])
    A00_table = SASCA_scan.State_Scan(ROUND, b_INP, np.array(b_C), np.array(b_D), np.array(b_A), np.array(b_B))
    prediction = get_prediction(A00_table)
    diff = (prediction != answer)
    wrong_bits = int(np.count_nonzero(diff))
    wrong_unknown = int(np.count_nonzero(diff[:unknown_bits]))
    wrong_known = int(np.count_nonzero(diff[unknown_bits:]))
    if wrong_bits<best_wrong_bits:
      best_wrong_bits = wrong_bits
      best_point = byte
      best_unknown_bits = unknown_bits
    if byte==0:
      baseline_wrong_bits = wrong_bits
    final_wrong_bits = wrong_bits
    final_unknown_wrong = wrong_unknown
    final_known_wrong = wrong_known
    final_unknown_bits = unknown_bits
    check = (wrong_bits<=ALLOWED_WRONG_BITS)
    if (byte%25==0) or (byte==RATE_POINT_COUNT-1):
      print('  unknown_bits={:4d}, known_bits={:4d}: wrong_bits={}, ber={:.4f}, wrong_unknown={}/{}, wrong_known={}/{}, success={}'.format(
        unknown_bits,
        answer_len-unknown_bits,
        wrong_bits,
        float(wrong_bits)/float(answer_len),
        wrong_unknown,
        unknown_bits,
        wrong_known,
        answer_len-unknown_bits,
        check
      ))
    Results.append(check)
  success_total = int(np.count_nonzero(Results))
  print('Trace {} summary: baseline_wrong_bits={}, best_wrong_bits={}@pt{}(unknown_bits={}), final_wrong_bits={}, best_ber={:.4f}, final_ber={:.4f}, delta_best_vs_baseline={}, delta_final_vs_baseline={}, final_unknown_wrong={}/{}, final_known_wrong={}/{}, success_count={}/{}'.format(
    str(tr).zfill(4),
    baseline_wrong_bits,
    best_wrong_bits,
    best_point,
    best_unknown_bits,
    final_wrong_bits,
    float(best_wrong_bits)/float(answer_len),
    float(final_wrong_bits)/float(answer_len),
    best_wrong_bits-baseline_wrong_bits,
    final_wrong_bits-baseline_wrong_bits,
    final_unknown_wrong,
    final_unknown_bits,
    final_known_wrong,
    answer_len-final_unknown_bits,
    success_total,
    RATE_POINT_COUNT
  ))
  print('Saving results')
  svm.Save(('Success/success_'+str(tr).zfill(4)+'.npy'), Results)
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


