import numpy as np
import os
import time


def Wait():
  print("Try again later.")
  time.sleep(300)
  return

def _raise_after_attempt(name, attempts, err):
  raise RuntimeError(
    "Failed after {} attempts while accessing {}: {}".format(attempts, name, err)
  ) from err


def Open(name, S, retries=1, sleep_seconds=2):
  for attempt in range(1, retries+1):
    try:
      return open(name, S)
    except Exception as err:
      if attempt>=retries:
        _raise_after_attempt(name, retries, err)
      print("Try again later.")
      time.sleep(sleep_seconds)


def Load(name, retries=1, sleep_seconds=2):
  for attempt in range(1, retries+1):
    try:
      return np.load(name)
    except Exception as err:
      if attempt>=retries:
        _raise_after_attempt(name, retries, err)
      print("Try again later.")
      time.sleep(sleep_seconds)


def Save(name, Obj, retries=2, sleep_seconds=1):
  for attempt in range(1, retries+1):
    try:
      parent = os.path.dirname(name)
      if parent:
        os.makedirs(parent, exist_ok=True)
      np.save(name, Obj)
      return
    except Exception as err:
      if attempt>=retries:
        _raise_after_attempt(name, retries, err)
      print("Try again later.")
      time.sleep(sleep_seconds)


def System(cmd, retries=2, sleep_seconds=1):
  for attempt in range(1, retries+1):
    status = os.system(cmd)
    if status==0:
      return
    if attempt>=retries:
      raise RuntimeError(
        "Command failed after {} attempts (exit {}): {}".format(retries, status, cmd)
      )
    print("Try again later.")
    time.sleep(sleep_seconds)

