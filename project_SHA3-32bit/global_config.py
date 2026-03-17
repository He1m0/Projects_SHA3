"""Centralized numeric parameters for the 32-bit SHA3 workflow.

Values can be overridden through environment variables when needed.
"""

import os
from pathlib import Path


def _load_dotenv_file(path):
  if not path.exists():
    return
  for raw_line in path.read_text().splitlines():
    line = raw_line.strip()
    if (not line) or line.startswith("#") or ("=" not in line):
      continue
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip().strip('"').strip("'")
    if key and (key not in os.environ):
      os.environ[key] = value


def _load_dotenv():
  root_dir = Path(__file__).resolve().parent
  _load_dotenv_file(root_dir / ".env")
  _load_dotenv_file(root_dir.parent / ".env")


_load_dotenv()


def _env_int(name, default):
  value = os.getenv(name)
  if value is None:
    return default
  try:
    return int(value)
  except ValueError as exc:
    raise ValueError("Invalid integer for {}: {}".format(name, value)) from exc


# Shared loop sizes.
INPUTS = _env_int("SHA3_INPUTS", 16)
INVOCATIONS = _env_int("SHA3_INVOCATIONS", 10)
VALIDATION_INPUTS = _env_int("SHA3_VALIDATION_INPUTS", 10)

# Reference generation and filtering parameters.
REFERENCE_FOLDERS = _env_int("SHA3_REFERENCE_FOLDERS", 1)
REFERENCE_TRACE_LEN = _env_int("SHA3_REFERENCE_TRACE_LEN", 13824)

# Detection preprocessing parameters.
DETECTION_TRACE_LEN = _env_int("SHA3_DETECTION_TRACE_LEN", 7500000)
DETECTION_SET_COUNT = _env_int("SHA3_DETECTION_SET_COUNT", 100)
TRAINING_SET_COUNT = _env_int("SHA3_TRAINING_SET_COUNT", 400)
VALIDATION_SET_COUNT = _env_int("SHA3_VALIDATION_SET_COUNT", 40)