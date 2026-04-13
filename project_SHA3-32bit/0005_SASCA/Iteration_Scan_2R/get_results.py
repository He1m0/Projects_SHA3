import numpy as np
import sys
import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve()
while not (ROOT_DIR / "global_config.py").exists() and ROOT_DIR != ROOT_DIR.parent:
  ROOT_DIR = ROOT_DIR.parent
if str(ROOT_DIR) not in sys.path:
  sys.path.insert(0, str(ROOT_DIR))
import global_config as gc

tag = '2R_B'
L = int(sys.argv[1])
U = int(sys.argv[2])

Block = []
for t in range(L, U):
  Sname = 'Success/success_'+str(t).zfill(4)+'.npy'
  Block.append(np.load(Sname))
Block = np.array(Block, dtype=np.int32)
Iterations = np.sum(Block, axis=0)
np.save(('iteration_scan_'+tag+'.npy'), Iterations)

trace_count = max(U-L, 1)
iter_axis = np.arange(len(Iterations))
success_rate = 100.0*Iterations/float(trace_count)
best_idx = int(np.argmax(Iterations))
print('Iteration scan {} summary'.format(tag))
print('  traces: {}'.format(U-L))
print('  points: {}'.format(len(Iterations)))
print('  best iteration: {} ({:.2f}%)'.format(best_idx, success_rate[best_idx]))
print('  final iteration: {} ({:.2f}%)'.format(int(iter_axis[-1]), success_rate[-1]))


