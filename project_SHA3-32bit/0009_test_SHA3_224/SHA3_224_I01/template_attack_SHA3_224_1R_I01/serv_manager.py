import numpy as np
import os
import time


def _raise_after_attempt(name, attempts, err):
  raise RuntimeError("Failed after " + str(attempts) + " attempts: " + str(name)) from err


def Open(name, S, retries=2, sleep_seconds=1):
  err = None
  for _ in range(retries):
    try:
      return open(name, S)
    except Exception as e:
      err = e
      time.sleep(sleep_seconds)
  _raise_after_attempt(name, retries, err)


def Load(name, retries=2, sleep_seconds=1):
  err = None
  for _ in range(retries):
    try:
      return np.load(name)
    except Exception as e:
      err = e
      time.sleep(sleep_seconds)
  _raise_after_attempt(name, retries, err)


def Save(name, Obj, retries=2, sleep_seconds=1):
  err = None
  parent = os.path.dirname(name)
  if parent:
    os.makedirs(parent, exist_ok=True)
  for _ in range(retries):
    try:
      np.save(name, Obj)
      return
    except Exception as e:
      err = e
      time.sleep(sleep_seconds)
  _raise_after_attempt(name, retries, err)


def System(cmd, retries=2, sleep_seconds=1):
  for attempt in range(retries):
    code = os.system(cmd)
    if code == 0:
      return
    if attempt < retries - 1:
      time.sleep(sleep_seconds)
  raise RuntimeError("Command failed after " + str(retries) + " attempts (exit " + str(code) + "): " + str(cmd))
