"""Policy loading. The file is located next to the code, not the working directory."""
import os
from pathlib import Path

DEFAULTS = {
    "age_band_years": 5,
    "wide_age_band_years": 20,
    "top_age": 90,
    "date_shift_max_days": 180,
    "date_shift_min_days": 15,
    "rare_diagnosis_max_patients": 2,
    "pin_digits_kept": 3,
    "max_json_depth": 60,
    "max_file_mb": 200,
}


def load_policy():
    policy = dict(DEFAULTS)
    path = Path(os.environ.get("RAKSHA_POLICY") or Path(__file__).resolve().parents[1] / "config" / "policy.yaml")
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            key, separator, value = line.split("#", 1)[0].partition(":")
            if separator and key.strip() in policy:
                policy[key.strip()] = int(value.strip())
    return policy
