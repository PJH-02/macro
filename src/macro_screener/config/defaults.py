from __future__ import annotations

from typing import Any

DEFAULT_CONFIG: dict[str, Any] = {
    "config_version": "mvp-1",
    "environment": "local",
    "paths": {
        "data_dir": "data",
        "log_dir": "data/logs",
        "snapshot_dir": "data/snapshots",
        "latest_snapshot_pointer": "data/snapshots/latest.json",
        "sqlite_path": "data/macro_screener.sqlite3",
    },
    "schedule": {
        "timezone": "Asia/Seoul",
        "pre_open_time": "08:30",
        "post_close_time": "15:45",
    },
    "universe": {
        "markets": ["KOSPI", "KOSDAQ"],
        "stock_classification_path": "stock_classification.csv",
    },
    "stage1": {
        "channels": ["G", "IC", "FC", "ED", "FX"],
        "manual_channel_states": {
            "G": 0,
            "IC": 0,
            "FC": 0,
            "ED": 0,
            "FX": 0,
        },
    },
    "stage2": {
        "score_weights": {"dart": 1.0, "industry": 0.35, "financial": 0.0},
        "decay_half_lives": {
            "supply_contract": 20,
            "treasury_stock": 10,
            "facility_investment": 60,
            "dilutive_financing": 60,
            "correction_cancellation_withdrawal": 10,
            "governance_risk": 120,
        },
    },
    "runtime": {
        "retries": 3,
        "scheduler_enabled": True,
        "dart_api_key_env": "DART_API_KEY",
        "stage1_only_on_stage2_failure": True,
        "stale_dart_after_retries": True,
        "reuse_last_known_channel_states": True,
        "unknown_dart_ratio_warning_threshold": 0.2,
        "max_runtime_minutes_warning": 5,
    },
}
