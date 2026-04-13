import numpy as np
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve()
while not (ROOT_DIR / "global_config.py").exists() and ROOT_DIR != ROOT_DIR.parent:
  ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))
import global_config as gc

tag = '3R_B'
L = int(sys.argv[1])
U = int(sys.argv[2])

block = []
results = []
for t in range(L, U):
  tname = 'Success/success_'+str(t).zfill(4)+'.npy'
  print(tname)
  block.append(np.load(tname))
block = np.vstack(block)
for r in range(0, gc.SASCA_RATE_POINT_COUNT):
  results.append(np.count_nonzero(block[:,r]))
np.save(('rate_scan_'+tag+'.npy'), results)

trace_count = max(U-L, 1)
rates = gc.SASCA_RATE_STEP_BITS*np.arange(len(results))
success_rate = 100.0*(np.array(results, dtype=np.float64)/float(trace_count))
best_idx = int(np.argmax(results))
print('Rate scan {} summary'.format(tag))
print('  traces: {}'.format(U-L))
print('  points: {}'.format(len(results)))
print('  best rate: {} bits ({:.2f}%)'.format(int(rates[best_idx]), success_rate[best_idx]))
print('  final rate: {} bits ({:.2f}%)'.format(int(rates[-1]), success_rate[-1]))


