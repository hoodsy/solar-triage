"""Prediction-datum field names, isolated so a rename is a one-line change.

These are provisional pending Thomas (Ecosuite): the status key carrying the
label, the meta key names, and the prediction source-id convention.
"""

FAULT_CLASS_KEY = "faultClass"  # status ("s") property carrying the day label
META_CONFIDENCE = "confidence"
META_HISTORY_DAYS = "history_days"
META_MODEL_VERSION = "model_version"
DEFAULT_PREDICTION_SOURCE_ID = "/triage/1"
