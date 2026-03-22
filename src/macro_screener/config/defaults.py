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
        "industry_master_path": "data/reference/industry_master.csv",
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
        "rank_table_artifact_path": "config/stage1_sector_rank_tables.v1.json",
        "channel_weights": {"G": 1.0, "IC": 1.0, "FC": 1.0, "ED": 1.0, "FX": 1.0},
        "neutral_bands": {"G": 0.25, "IC": 0.25, "FC": 0.25, "ED": 0.25, "FX": 0.5},
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
        "normal_mode": "live",
        "dart_api_key_env": "DART_API_KEY",
        "ecos_api_key_env": "ECOS_API_KEY",
        "fred_api_key_env": "FRED_API_KEY",
        "kosis_api_key_env": "KOSIS_API_KEY",
        "krx_api_key_env": "KRX_API_KEY",
        "allow_manual_macro_states_in_live_mode": False,
        "allow_local_file_inputs_in_live_mode": False,
        "stage1_only_on_stage2_failure": True,
        "stale_dart_after_retries": True,
        "reuse_last_known_channel_states": True,
        "unknown_dart_ratio_warning_threshold": 0.2,
        "max_runtime_minutes_warning": 5,
    },
}
