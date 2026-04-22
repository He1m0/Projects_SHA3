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
    if key:
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


def _env_float(name, default):
  value = os.getenv(name)
  if value is None:
    return default
  try:
    return float(value)
  except ValueError as exc:
    raise ValueError("Invalid float for {}: {}".format(name, value)) from exc


def _env_float_list(name, default):
  value = os.getenv(name)
  if value is None:
    return default
  values = []
  for item in value.split(","):
    stripped = item.strip()
    if not stripped:
      continue
    try:
      values.append(float(stripped))
    except ValueError as exc:
      raise ValueError("Invalid float list item for {}: {}".format(name, stripped)) from exc
  if len(values)==0:
    raise ValueError("Invalid float list for {}: {}".format(name, value))
  return values


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
DETECTION_SETS_PER_PART = _env_int("SHA3_DETECTION_SETS_PER_PART", 25)
DETECTION_PART_COUNT = (DETECTION_SET_COUNT + DETECTION_SETS_PER_PART - 1) // DETECTION_SETS_PER_PART
DETECTION_CORR_BOUND = _env_float("SHA3_DETECTION_CORR_BOUND", 0.98)
DETECTION_TRACE_OFFSET = _env_int("SHA3_DETECTION_TRACE_OFFSET", 75000 + 455)
DETECTION_PPC = _env_int("SHA3_DETECTION_PPC", 500)
DETECTION_OUTPUT_SIZE = _env_int("SHA3_DETECTION_OUTPUT_SIZE", 14500)
DETECTION_SAMPLE_SHIFT = _env_int("SHA3_DETECTION_SAMPLE_SHIFT", 20)
DETECTION_SAMPLE_WIDTH = _env_int("SHA3_DETECTION_SAMPLE_WIDTH", 50)
DETECTION_ROUNDS = _env_int("SHA3_DETECTION_ROUNDS", 4)
DETECTION_ICS_WORDS_AB = _env_int("SHA3_DETECTION_ICS_WORDS_AB", 50)
DETECTION_ICS_WORDS_CD = _env_int("SHA3_DETECTION_ICS_WORDS_CD", 10)
DETECTION_ICS_THRESHOLDS = _env_float_list(
  "SHA3_DETECTION_ICS_THRESHOLDS",
  [0.09, 0.08, 0.07, 0.06, 0.05, 0.04, 0.03, 0.02, 0.01]
)
TRAINING_SET_COUNT = _env_int("SHA3_TRAINING_SET_COUNT", 400)
VALIDATION_SET_COUNT = _env_int("SHA3_VALIDATION_SET_COUNT", 40)

# Training preprocessing / packaging parameters.
TRAINING_TRACE_OFFSET = _env_int("SHA3_TRAINING_TRACE_OFFSET", 75455)
# Prefer SHA3_TRAINING_PPC; keep SHA3_TRAINING_RESAMPLE_WIDTH as a legacy alias.
TRAINING_PPC = _env_int("SHA3_TRAINING_PPC", _env_int("SHA3_TRAINING_RESAMPLE_WIDTH", 50))
TRAINING_OUTPUT_SIZE = _env_int("SHA3_TRAINING_OUTPUT_SIZE", 145000)
TRAINING_SETS_PER_PART = _env_int("SHA3_TRAINING_SETS_PER_PART", 25)
TRAINING_PART_COUNT = (TRAINING_SET_COUNT + TRAINING_SETS_PER_PART - 1) // TRAINING_SETS_PER_PART
TRAINING_CORR_BOUND = _env_float("SHA3_TRAINING_CORR_BOUND", 0.98)
TRAINING_ICS_LEVEL = _env_int("SHA3_TRAINING_ICS_LEVEL", 10)

# Validation preprocessing / packaging parameters.
VALIDATION_TRACE_OFFSET = _env_int("SHA3_VALIDATION_TRACE_OFFSET", 75000 + 455)
VALIDATION_PPC = _env_int("SHA3_VALIDATION_PPC", 500)
VALIDATION_OUTPUT_SIZE = _env_int("SHA3_VALIDATION_OUTPUT_SIZE", 14500 * 10)
VALIDATION_CORR_BOUND = _env_float("SHA3_VALIDATION_CORR_BOUND", 0.98)
VALIDATION_SETS_PER_PART = _env_int("SHA3_VALIDATION_SETS_PER_PART", 10)
VALIDATION_PART_COUNT = (VALIDATION_SET_COUNT + VALIDATION_SETS_PER_PART - 1) // VALIDATION_SETS_PER_PART
VALIDATION_TEMPLATE_TAG = str(_env_int("SHA3_VALIDATION_TEMPLATE_TAG", 10)).zfill(3)
VALIDATION_ICS_TAG = str(_env_int("SHA3_VALIDATION_ICS_TAG", TRAINING_ICS_LEVEL)).zfill(3)

# Derived resampling ratios: each detection-processed column aggregates this
# many training/validation-processed columns. Used when translating ICS
# indices (detection column space) into the finer training/validation grids.
TRAINING_ICS_WINDOW = max(1, DETECTION_PPC // TRAINING_PPC)
VALIDATION_ICS_WINDOW = max(1, DETECTION_PPC // VALIDATION_PPC)

# LDA within-class covariance degrees-of-freedom correction. The Scov
# denominator is (Total_Tnum - TEMPLATE_LDA_DOF). Default 9 matches the
# original paper (8 bit features + intercept); lower it for aggressive
# covariance shrinkage, raise it to reduce trust in small-N training sets.
TEMPLATE_LDA_DOF = _env_int("SHA3_TEMPLATE_LDA_DOF", 9)

# 0005_SASCA parameters.
VALIDATION_TRACE_COUNT = VALIDATION_SET_COUNT * VALIDATION_INPUTS * INVOCATIONS
SASCA_TRACE_COUNT = _env_int("SHA3_SASCA_TRACE_COUNT", min(1000, VALIDATION_TRACE_COUNT))
SASCA_TEMPLATE_TAG = str(_env_int("SHA3_SASCA_TEMPLATE_TAG", int(VALIDATION_TEMPLATE_TAG))).zfill(3)
SASCA_ICS_TAG = str(_env_int("SHA3_SASCA_ICS_TAG", int(VALIDATION_ICS_TAG))).zfill(3)
SASCA_PPC = _env_int("SHA3_SASCA_PPC", VALIDATION_ICS_WINDOW)

# 0005 scan controls.
SASCA_ITERATION_COUNT = _env_int("SHA3_SASCA_ITERATION_COUNT", 40)
SASCA_RATE_BP_ITERATION_COUNT = _env_int("SHA3_SASCA_RATE_BP_ITERATION_COUNT", 200)
SASCA_RATE_POINT_COUNT = _env_int("SHA3_SASCA_RATE_POINT_COUNT", 201)
SASCA_RATE_STEP_BITS = _env_int("SHA3_SASCA_RATE_STEP_BITS", 8)
SASCA_ALLOWED_WRONG_BITS = _env_int("SHA3_SASCA_ALLOWED_WRONG_BITS", 0)
SASCA_OUTPUT_BITS = _env_int("SHA3_SASCA_OUTPUT_BITS", 512)
SASCA_KNOWN_RATE_BITS = 1600 - (2 * SASCA_OUTPUT_BITS)