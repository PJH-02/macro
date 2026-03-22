from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from macro_screener.serialization import SerializableMixin


@dataclass(frozen=True, slots=True)
class PathConfig(SerializableMixin):
    data_dir: str = "data"
    log_dir: str = "data/logs"
    snapshot_dir: str = "data/snapshots"
    latest_snapshot_pointer: str = "data/snapshots/latest.json"
    sqlite_path: str = "data/macro_screener.sqlite3"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PathConfig":
        return cls(
            data_dir=str(payload.get("data_dir", "data")),
            log_dir=str(payload.get("log_dir", "data/logs")),
            snapshot_dir=str(payload.get("snapshot_dir", "data/snapshots")),
            latest_snapshot_pointer=str(
                payload.get("latest_snapshot_pointer", "data/snapshots/latest.json")
            ),
            sqlite_path=str(payload.get("sqlite_path", "data/macro_screener.sqlite3")),
        )

    def resolve(self, relative_path: str, base_path: Path) -> Path:
        path = Path(relative_path)
        return path if path.is_absolute() else base_path / path


@dataclass(frozen=True, slots=True)
class ScheduleConfig(SerializableMixin):
    timezone: str = "Asia/Seoul"
    pre_open_time: str = "08:30"
    post_close_time: str = "15:45"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ScheduleConfig":
        return cls(
            timezone=str(payload.get("timezone", "Asia/Seoul")),
            pre_open_time=str(payload.get("pre_open_time", "08:30")),
            post_close_time=str(payload.get("post_close_time", "15:45")),
        )


@dataclass(frozen=True, slots=True)
class UniverseConfig(SerializableMixin):
    markets: tuple[str, ...] = ("KOSPI", "KOSDAQ")
    stock_classification_path: str = "stock_classification.csv"
    industry_master_path: str = "data/reference/industry_master.csv"

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "UniverseConfig":
        markets = tuple(str(item) for item in payload.get("markets", ["KOSPI", "KOSDAQ"]))
        return cls(
            markets=markets,
            stock_classification_path=str(
                payload.get("stock_classification_path", "stock_classification.csv")
            ),
            industry_master_path=str(
                payload.get("industry_master_path", "data/reference/industry_master.csv")
            ),
        )


@dataclass(frozen=True, slots=True)
class Stage1Config(SerializableMixin):
    channels: tuple[str, ...] = ("G", "IC", "FC", "ED", "FX")
    manual_channel_states: dict[str, int] = field(
        default_factory=lambda: {"G": 0, "IC": 0, "FC": 0, "ED": 0, "FX": 0}
    )
    rank_table_artifact_path: str = "config/stage1_sector_rank_tables.v1.json"
    channel_weights: dict[str, float] = field(
        default_factory=lambda: {"G": 1.0, "IC": 1.0, "FC": 1.0, "ED": 1.0, "FX": 1.0}
    )
    neutral_bands: dict[str, float] = field(
        default_factory=lambda: {"G": 0.25, "IC": 0.25, "FC": 0.25, "ED": 0.25, "FX": 0.5}
    )

    def __post_init__(self) -> None:
        if set(self.channels) != {"G", "IC", "FC", "ED", "FX"}:
            raise ValueError("Stage1 channels must exactly match the MVP channel set.")
        invalid_values = {
            state for state in self.manual_channel_states.values() if state not in {-1, 0, 1}
        }
        if invalid_values:
            raise ValueError(f"Invalid manual channel state values: {sorted(invalid_values)}")
        if set(self.channel_weights) != set(self.channels):
            raise ValueError("Stage1 channel weights must cover the MVP channel set exactly.")
        if set(self.neutral_bands) != set(self.channels):
            raise ValueError("Stage1 neutral bands must cover the MVP channel set exactly.")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Stage1Config":
        manual_states = {
            str(key): int(value)
            for key, value in payload.get(
                "manual_channel_states",
                {"G": 0, "IC": 0, "FC": 0, "ED": 0, "FX": 0},
            ).items()
        }
        channel_weights = {
            str(key): float(value)
            for key, value in payload.get(
                "channel_weights",
                {"G": 1.0, "IC": 1.0, "FC": 1.0, "ED": 1.0, "FX": 1.0},
            ).items()
        }
        neutral_bands = {
            str(key): float(value)
            for key, value in payload.get(
                "neutral_bands",
                {"G": 0.25, "IC": 0.25, "FC": 0.25, "ED": 0.25, "FX": 0.5},
            ).items()
        }
        return cls(
            channels=tuple(
                str(item) for item in payload.get("channels", ["G", "IC", "FC", "ED", "FX"])
            ),
            manual_channel_states=manual_states,
            rank_table_artifact_path=str(
                payload.get("rank_table_artifact_path", "config/stage1_sector_rank_tables.v1.json")
            ),
            channel_weights=channel_weights,
            neutral_bands=neutral_bands,
        )


@dataclass(frozen=True, slots=True)
class Stage2Config(SerializableMixin):
    score_weights: dict[str, float] = field(
        default_factory=lambda: {"dart": 1.0, "industry": 0.35, "financial": 0.0}
    )
    decay_half_lives: dict[str, int] = field(
        default_factory=lambda: {
            "supply_contract": 20,
            "treasury_stock": 10,
            "facility_investment": 60,
            "dilutive_financing": 60,
            "correction_cancellation_withdrawal": 10,
            "governance_risk": 120,
        }
    )

    def __post_init__(self) -> None:
        missing = {
            "supply_contract",
            "treasury_stock",
            "facility_investment",
            "dilutive_financing",
            "correction_cancellation_withdrawal",
            "governance_risk",
        } - set(self.decay_half_lives)
        if missing:
            raise ValueError(f"Missing stage2 decay half-life defaults: {sorted(missing)}")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "Stage2Config":
        score_weights = {
            str(key): float(value)
            for key, value in payload.get(
                "score_weights",
                {"dart": 1.0, "industry": 0.35, "financial": 0.0},
            ).items()
        }
        decay_half_lives = {
            str(key): int(value)
            for key, value in payload.get(
                "decay_half_lives",
                {
                    "supply_contract": 20,
                    "treasury_stock": 10,
                    "facility_investment": 60,
                    "dilutive_financing": 60,
                    "correction_cancellation_withdrawal": 10,
                    "governance_risk": 120,
                },
            ).items()
        }
        return cls(score_weights=score_weights, decay_half_lives=decay_half_lives)


@dataclass(frozen=True, slots=True)
class RuntimePolicyConfig(SerializableMixin):
    retries: int = 3
    scheduler_enabled: bool = True
    normal_mode: str = "live"
    dart_api_key_env: str = "DART_API_KEY"
    ecos_api_key_env: str = "ECOS_API_KEY"
    fred_api_key_env: str = "FRED_API_KEY"
    kosis_api_key_env: str = "KOSIS_API_KEY"
    krx_api_key_env: str = "KRX_API_KEY"
    allow_manual_macro_states_in_live_mode: bool = False
    allow_local_file_inputs_in_live_mode: bool = False
    stage1_only_on_stage2_failure: bool = True
    stale_dart_after_retries: bool = True
    reuse_last_known_channel_states: bool = True
    unknown_dart_ratio_warning_threshold: float = 0.2
    max_runtime_minutes_warning: int = 5

    def __post_init__(self) -> None:
        if self.normal_mode not in {"live", "degraded"}:
            raise ValueError("Runtime normal_mode must be 'live' or 'degraded'.")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "RuntimePolicyConfig":
        return cls(
            retries=int(payload.get("retries", 3)),
            scheduler_enabled=bool(payload.get("scheduler_enabled", True)),
            normal_mode=str(payload.get("normal_mode", "live")),
            dart_api_key_env=str(payload.get("dart_api_key_env", "DART_API_KEY")),
            ecos_api_key_env=str(payload.get("ecos_api_key_env", "ECOS_API_KEY")),
            fred_api_key_env=str(payload.get("fred_api_key_env", "FRED_API_KEY")),
            kosis_api_key_env=str(payload.get("kosis_api_key_env", "KOSIS_API_KEY")),
            krx_api_key_env=str(payload.get("krx_api_key_env", "KRX_API_KEY")),
            allow_manual_macro_states_in_live_mode=bool(
                payload.get("allow_manual_macro_states_in_live_mode", False)
            ),
            allow_local_file_inputs_in_live_mode=bool(
                payload.get("allow_local_file_inputs_in_live_mode", False)
            ),
            stage1_only_on_stage2_failure=bool(payload.get("stage1_only_on_stage2_failure", True)),
            stale_dart_after_retries=bool(payload.get("stale_dart_after_retries", True)),
            reuse_last_known_channel_states=bool(
                payload.get("reuse_last_known_channel_states", True)
            ),
            unknown_dart_ratio_warning_threshold=float(
                payload.get("unknown_dart_ratio_warning_threshold", 0.2)
            ),
            max_runtime_minutes_warning=int(payload.get("max_runtime_minutes_warning", 5)),
        )


@dataclass(frozen=True, slots=True)
class AppConfig(SerializableMixin):
    config_version: str
    environment: str
    paths: PathConfig
    schedule: ScheduleConfig
    universe: UniverseConfig
    stage1: Stage1Config
    stage2: Stage2Config
    runtime: RuntimePolicyConfig

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "AppConfig":
        return cls(
            config_version=str(payload.get("config_version", "mvp-1")),
            environment=str(payload.get("environment", "local")),
            paths=PathConfig.from_dict(dict(payload.get("paths", {}))),
            schedule=ScheduleConfig.from_dict(dict(payload.get("schedule", {}))),
            universe=UniverseConfig.from_dict(dict(payload.get("universe", {}))),
            stage1=Stage1Config.from_dict(dict(payload.get("stage1", {}))),
            stage2=Stage2Config.from_dict(dict(payload.get("stage2", {}))),
            runtime=RuntimePolicyConfig.from_dict(dict(payload.get("runtime", {}))),
        )
