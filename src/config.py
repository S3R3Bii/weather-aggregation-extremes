"""Fixed historical sample aggregation, not continuous exposure or product risk."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEVELOPMENT_YEARS = list(range(2010, 2017))
EVALUATION_YEARS = list(range(2017, 2025))
YEARS = DEVELOPMENT_YEARS + EVALUATION_YEARS
THRESHOLDS = [25, 30, 35]
SEED = 20261029
REPLICATES = 500
