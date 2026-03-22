from __future__ import annotations

import inspect
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from macro_screener.config import AppConfig, load_config
from macro_screener.data.dart_client import DARTClient, DARTLoadResult
from macro_screener.data.krx_client import KRXClient
from macro_screener.data.macro_client import (
    DEFAULT_CHANNEL_STATES,
    ManualMacroDataSource,
    PersistedMacroDataSource,
)
from macro_screener.models import RunMode, RunType, ScheduledWindowKey, Snapshot, SnapshotStatus
from macro_screener.pipeline.publisher import publish_snapshot
from macro_screener.pipeline.runtime import bootstrap_runtime
from macro_screener.pipeline.scheduler import build_scheduled_context
from macro_screener.serialization import parse_datetime
from macro_screener.stage1.overlay import DEFAULT_OVERLAYS
from macro_screener.stage1.ranking import compute_stage1_result
from macro_screener.stage2.ranking import compute_stock_scores

DEFAULT_DEMO_RUN_ID = "manual-demo-20260321T083000KST"
DEFAULT_DEMO_RUN_TYPE = RunType.MANUAL.value
DEFAULT_DEMO_AS_OF = "2026-03-21T08:30:00+09:00"
DEFAULT_DEMO_INPUT_CUTOFF = "2026-03-20T18:00:00+09:00"
DEFAULT_CONFIG_VERSION = "mvp-1"
KST = ZoneInfo("Asia/Seoul")


def build_manual_context(
    *,
    run_id: str | None = None,
    run_type: str = RunType.MANUAL.value,
    as_of_timestamp: str | datetime | None = None,
    input_cutoff: str | datetime | None = None,
    published_at: str | datetime | None = None,
) -> dict[str, str]:
    as_of_dt = parse_datetime(as_of_timestamp) if as_of_timestamp is not None else datetime.now(KST)
    cutoff_dt = parse_datetime(input_cutoff) if input_cutoff is not None else as_of_dt
    published_dt = parse_datetime(published_at) if published_at is not None else as_of_dt
    resolved_run_id = run_id or f"manual-{published_dt.astimezone(KST).strftime('%Y%m%dT%H%M%S%z')}"
    return {
        "run_id": resolved_run_id,
        "run_type": run_type,
        "as_of_timestamp": as_of_dt.isoformat(),
        "input_cutoff": cutoff_dt.isoformat(),
        "published_at": published_dt.isoformat(),
    }


def build_demo_snapshot(
    *,
    run_id: str = DEFAULT_DEMO_RUN_ID,
    run_type: str = DEFAULT_DEMO_RUN_TYPE,
    as_of_timestamp: str = DEFAULT_DEMO_AS_OF,
    input_cutoff: str = DEFAULT_DEMO_INPUT_CUTOFF,
    published_at: str = DEFAULT_DEMO_AS_OF,
    channel_states: dict[str, int] | None = None,
) -> Snapshot:
    context = build_manual_context(
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
        input_cutoff=input_cutoff,
        published_at=published_at,
    )
    stage1_result = compute_stage1_result(
        channel_states=channel_states or DEFAULT_CHANNEL_STATES,
        exposures=KRXClient(use_demo_fallback=True).load_demo_exposures(),
        overlay_adjustments=DEFAULT_OVERLAYS,
        run_id=context["run_id"],
        run_type=context["run_type"],
        as_of_timestamp=context["as_of_timestamp"],
        config_version=DEFAULT_CONFIG_VERSION,
        channel_state_source="demo_manual",
    )
    stock_scores, warnings = compute_stock_scores(
        stage1_result=stage1_result,
        stocks=KRXClient(use_demo_fallback=True).load_demo_stocks(),
        disclosures=DARTClient(use_demo_fallback=True).load_demo_disclosures(),
    )
    return Snapshot(
        run_id=context["run_id"],
        run_type=RunType(context["run_type"]),
        as_of_timestamp=parse_datetime(context["as_of_timestamp"]),
        input_cutoff=parse_datetime(context["input_cutoff"]),
        published_at=parse_datetime(context["published_at"]),
        status=SnapshotStatus.PUBLISHED,
        industry_scores=stage1_result.industry_scores,
        stock_scores=stock_scores,
        warnings=[*stage1_result.warnings, *warnings],
    )


def _resolve_config(config_path: str | Path | None) -> AppConfig:
    return load_config(config_path)


def _repo_relative(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else Path.cwd() / path


def _scheduled_window_key_text(context: Mapping[str, Any]) -> str | None:
    value = context.get("scheduled_window_key_text")
    return None if value is None else str(value)


def _scheduled_window_key(context: Mapping[str, Any]) -> ScheduledWindowKey | None:
    payload = context.get("scheduled_window_key")
    if not isinstance(payload, Mapping):
        return None
    return ScheduledWindowKey.from_dict(dict(payload))


def _resolve_macro_states(
    *,
    config: AppConfig,
    store: Any,
    channel_states: dict[str, int] | None,
    use_demo_inputs: bool,
) -> tuple[dict[str, int], str, list[str]]:
    if channel_states is not None:
        merged_states = {**config.stage1.manual_channel_states, **channel_states}
        result = ManualMacroDataSource(
            merged_states,
            source_name="manual_override",
        ).fetch_channel_states()
        return result.channel_states, result.source, result.warnings
    if use_demo_inputs:
        result = ManualMacroDataSource(
            DEFAULT_CHANNEL_STATES,
            source_name="demo_manual",
        ).fetch_channel_states()
        return result.channel_states, result.source, result.warnings
    try:
        result = ManualMacroDataSource(
            config.stage1.manual_channel_states,
            source_name="manual_config",
        ).fetch_channel_states()
        return result.channel_states, result.source, result.warnings
    except ValueError:
        if config.runtime.reuse_last_known_channel_states:
            persisted = PersistedMacroDataSource(store).fetch_channel_states()
            return persisted.channel_states, persisted.source, persisted.warnings
        raise


def _load_disclosures(
    *,
    output_dir: Path,
    config: AppConfig,
    store: Any,
    input_cutoff: str,
    use_demo_inputs: bool,
) -> DARTLoadResult:
    if use_demo_inputs:
        return DARTLoadResult(
            disclosures=DARTClient(use_demo_fallback=True).load_demo_disclosures(),
            warnings=[],
            watermark=input_cutoff,
            source="demo",
        )
    client = DARTClient(api_key_env=config.runtime.dart_api_key_env)
    cache_path = output_dir / "data" / "cache" / "dart" / "latest.json"
    return client.load_disclosures(
        input_cutoff=input_cutoff,
        retries=config.runtime.retries,
        store=store,
        cache_path=cache_path,
        allow_stale=config.runtime.stale_dart_after_retries,
    )


def _channel_state_metadata_kwargs(
    *,
    context: Mapping[str, Any],
    config: AppConfig,
    macro_source: str,
    macro_warnings: list[str],
    use_demo_inputs: bool,
    channel_states: dict[str, int],
) -> dict[str, Any]:
    fallback_mode: str | None = None
    if use_demo_inputs:
        fallback_mode = "demo"
    elif macro_source == "last_known":
        fallback_mode = "last_known_channel_states"
    warning_map = (
        {channel: list(macro_warnings) for channel in channel_states}
        if macro_warnings
        else None
    )
    kwargs: dict[str, Any] = {
        "input_cutoff": str(context["input_cutoff"]),
        "channel_state_source_version": config.config_version,
        "channel_state_fallback_mode": fallback_mode,
        "channel_state_warning_flags": warning_map,
    }
    return kwargs


def _compute_stage1_result_compat(
    *,
    channel_states: dict[str, int],
    exposures: list[dict[str, Any]],
    overlay_adjustments: dict[str, float],
    context: Mapping[str, Any],
    config: AppConfig,
    macro_source: str,
    macro_warnings: list[str],
    use_demo_inputs: bool,
) -> Any:
    kwargs: dict[str, Any] = {
        "channel_states": channel_states,
        "exposures": exposures,
        "overlay_adjustments": overlay_adjustments,
        "run_id": str(context["run_id"]),
        "run_type": str(context["run_type"]),
        "as_of_timestamp": str(context["as_of_timestamp"]),
        "config_version": config.config_version,
        "channel_state_source": macro_source,
    }
    optional_kwargs = _channel_state_metadata_kwargs(
        context=context,
        config=config,
        macro_source=macro_source,
        macro_warnings=macro_warnings,
        use_demo_inputs=use_demo_inputs,
        channel_states=channel_states,
    )
    supported = inspect.signature(compute_stage1_result).parameters
    for key, value in optional_kwargs.items():
        if key in supported and value is not None:
            kwargs[key] = value
    return compute_stage1_result(**kwargs)


def _channel_state_snapshot_metadata(
    *,
    context: Mapping[str, Any],
    config: AppConfig,
    macro_source: str,
    macro_warnings: list[str],
    use_demo_inputs: bool,
) -> dict[str, Any]:
    fallback_mode: str | None = None
    if use_demo_inputs:
        fallback_mode = "demo"
    elif macro_source == "last_known":
        fallback_mode = "last_known_channel_states"
    return {
        "source_name": macro_source,
        "source_version": config.config_version,
        "fallback_mode": fallback_mode,
        "as_of_timestamp": str(context["as_of_timestamp"]),
        "input_cutoff": str(context["input_cutoff"]),
        "warning_flags": list(macro_warnings),
    }


def run_pipeline_context(
    output_dir: str | Path,
    *,
    context: Mapping[str, Any],
    mode: RunMode,
    config_path: str | Path | None = None,
    channel_states: dict[str, int] | None = None,
    use_demo_inputs: bool = False,
) -> dict[str, Any]:
    output_root = Path(output_dir)
    config = _resolve_config(config_path)
    bootstrap = bootstrap_runtime(config, output_root)
    store = bootstrap.store

    scheduled_key_text = _scheduled_window_key_text(context)
    scheduled_key = _scheduled_window_key(context)
    if scheduled_key_text is not None:
        published = store.published_snapshot_for_window(scheduled_key_text)
        if published is not None:
            return {
                "context": dict(context),
                "mode": mode.value,
                "snapshot": {
                    "run_id": context["run_id"],
                    "status": SnapshotStatus.DUPLICATE.value,
                    "scheduled_window_key": scheduled_key_text,
                },
                "latest": published,
                "warnings": ["duplicate_scheduled_window_skipped"],
            }

    macro_states, macro_source, macro_warnings = _resolve_macro_states(
        config=config,
        store=store,
        channel_states=channel_states,
        use_demo_inputs=use_demo_inputs,
    )
    warnings = list(macro_warnings)
    krx_client = KRXClient(
        stock_classification_path=_repo_relative(config.universe.stock_classification_path),
        use_demo_fallback=True,
    )
    exposure_result = krx_client.load_exposures_result()
    if not use_demo_inputs:
        warnings.extend(exposure_result.warnings)
    stage1_result = _compute_stage1_result_compat(
        channel_states=macro_states,
        exposures=exposure_result.rows,
        overlay_adjustments=DEFAULT_OVERLAYS,
        context=context,
        config=config,
        macro_source=macro_source,
        macro_warnings=macro_warnings,
        use_demo_inputs=use_demo_inputs,
    )
    store.save_channel_states(
        run_id=stage1_result.run_id,
        channel_states=stage1_result.channel_states,
        source=macro_source,
        metadata=_channel_state_snapshot_metadata(
            context=context,
            config=config,
            macro_source=macro_source,
            macro_warnings=macro_warnings,
            use_demo_inputs=use_demo_inputs,
        ),
    )

    disclosure_result = _load_disclosures(
        output_dir=output_root,
        config=config,
        store=store,
        input_cutoff=str(context["input_cutoff"]),
        use_demo_inputs=use_demo_inputs,
    )
    warnings.extend(disclosure_result.warnings)
    stage2_status = SnapshotStatus.PUBLISHED
    stock_result = krx_client.load_stocks_result()
    if not use_demo_inputs:
        warnings.extend(stock_result.warnings)
    stocks = stock_result.rows
    known_industries = {score.industry_code for score in stage1_result.industry_scores}
    if not any(str(stock["industry_code"]) in known_industries for stock in stocks):
        stocks = krx_client.load_demo_stocks()
        warnings.append("stock_universe_unmapped_using_demo_stocks")
    try:
        stock_scores, stage2_warnings = compute_stock_scores(
            stage1_result=stage1_result,
            stocks=stocks,
            disclosures=disclosure_result.disclosures,
            lambda_weight=config.stage2.score_weights["industry"],
            unknown_ratio_warning_threshold=config.runtime.unknown_dart_ratio_warning_threshold,
        )
        warnings.extend(stage2_warnings)
    except Exception as exc:
        if not config.runtime.stage1_only_on_stage2_failure:
            raise
        stock_scores = []
        stage2_status = SnapshotStatus.INCOMPLETE
        warnings.append(f"stage2_failed_publishing_stage1_only: {exc}")

    snapshot = Snapshot(
        run_id=str(context["run_id"]),
        run_type=RunType(str(context["run_type"])),
        as_of_timestamp=parse_datetime(str(context["as_of_timestamp"])),
        input_cutoff=parse_datetime(str(context["input_cutoff"])),
        published_at=parse_datetime(str(context["published_at"])),
        status=stage2_status,
        industry_scores=stage1_result.industry_scores,
        stock_scores=stock_scores,
        warnings=warnings,
    )

    latest_payload: dict[str, str] | None = None
    publish_error: Exception | None = None
    for _ in range(2):
        try:
            latest_payload = publish_snapshot(
                snapshot,
                output_root,
                config=config,
                store=store,
                scheduled_window_key=scheduled_key_text,
            )
            publish_error = None
            break
        except Exception as exc:
            publish_error = exc
    if publish_error is not None:
        raise publish_error

    return {
        "context": dict(context),
        "mode": mode.value,
        "snapshot": snapshot.to_dict(),
        "latest": latest_payload,
        "warnings": warnings,
        "scheduled_window_key": scheduled_key.to_dict() if scheduled_key is not None else None,
    }


def run_manual(
    output_dir: str | Path,
    *,
    run_id: str | None = None,
    run_type: str = RunType.MANUAL.value,
    as_of_timestamp: str | datetime | None = None,
    input_cutoff: str | datetime | None = None,
    published_at: str | datetime | None = None,
    channel_states: dict[str, int] | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    context = build_manual_context(
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
        input_cutoff=input_cutoff,
        published_at=published_at,
    )
    return run_pipeline_context(
        output_dir,
        context=context,
        mode=RunMode.MANUAL,
        config_path=config_path,
        channel_states=channel_states,
    )


def run_demo(
    output_dir: str | Path,
    *,
    run_id: str = DEFAULT_DEMO_RUN_ID,
    run_type: str = DEFAULT_DEMO_RUN_TYPE,
    as_of_timestamp: str = DEFAULT_DEMO_AS_OF,
    input_cutoff: str = DEFAULT_DEMO_INPUT_CUTOFF,
    published_at: str = DEFAULT_DEMO_AS_OF,
) -> dict[str, Any]:
    context = build_manual_context(
        run_id=run_id,
        run_type=run_type,
        as_of_timestamp=as_of_timestamp,
        input_cutoff=input_cutoff,
        published_at=published_at,
    )
    return run_pipeline_context(
        output_dir,
        context=context,
        mode=RunMode.MANUAL,
        channel_states=DEFAULT_CHANNEL_STATES,
        use_demo_inputs=True,
    )


def run_scheduled(
    output_dir: str | Path,
    *,
    trading_date: str,
    run_type: str,
    attempted_at: str | datetime | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    context = build_scheduled_context(trading_date, run_type, attempted_at=attempted_at)
    return run_pipeline_context(
        output_dir,
        context=context,
        mode=RunMode.SCHEDULED,
        config_path=config_path,
    )


def run_scheduled_stub(
    output_dir: str | Path,
    *,
    trading_date: str,
    run_type: str,
    attempted_at: str | datetime | None = None,
    config_path: str | Path | None = None,
) -> dict[str, Any]:
    return run_scheduled(
        output_dir,
        trading_date=trading_date,
        run_type=run_type,
        attempted_at=attempted_at,
        config_path=config_path,
    )
