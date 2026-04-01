"""External data-source boundaries for KRX, DART, and macro providers."""

from macro_screener.data.dart_client import DEFAULT_DISCLOSURES, DARTClient, DARTLoadResult
from macro_screener.data.krx_client import DEFAULT_EXPOSURES, DEFAULT_STOCKS, KRXClient
from macro_screener.data.macro_client import (
    CHANNELS,
    DEFAULT_CHANNEL_STATES,
    MacroDataSource,
    MacroLoadResult,
    ManualMacroDataSource,
    PersistedMacroDataSource,
    last_known_channel_states,
)
from macro_screener.data.reference import (
    DEFAULT_CHANNEL_WEIGHTS,
    DEFAULT_NEUTRAL_BANDS,
    build_industry_master_records,
    build_grouped_sector_rank_table_compat_artifact,
    build_provisional_stage1_artifact,
    write_industry_master_csv,
    write_stage1_artifact_json,
)

__all__ = [
    "CHANNELS",
    "DARTClient",
    "DARTLoadResult",
    "DEFAULT_CHANNEL_STATES",
    "DEFAULT_CHANNEL_WEIGHTS",
    "DEFAULT_DISCLOSURES",
    "DEFAULT_EXPOSURES",
    "DEFAULT_NEUTRAL_BANDS",
    "DEFAULT_STOCKS",
    "KRXClient",
    "MacroDataSource",
    "MacroLoadResult",
    "ManualMacroDataSource",
    "PersistedMacroDataSource",
    "build_grouped_sector_rank_table_compat_artifact",
    "build_industry_master_records",
    "build_provisional_stage1_artifact",
    "last_known_channel_states",
    "write_industry_master_csv",
    "write_stage1_artifact_json",
]
