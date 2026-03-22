from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from macro_screener.data.dart_client import DARTLoadResult
from macro_screener.data.krx_client import KRXLoadResult
from macro_screener.data.macro_client import DEFAULT_CHANNEL_STATES, MacroLoadResult
from macro_screener.pipeline.runner import run_manual


def _write_production_config(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                'environment: "production"',
                "runtime:",
                '  normal_mode: "live"',
            ]
        ),
        encoding="utf-8",
    )


def test_production_live_mode_rejects_manual_macro_defaults(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "default.yaml"
    _write_production_config(config_path)

    with pytest.raises(
        RuntimeError,
        match="manual_macro_source_forbidden_in_production_live_mode:manual_config",
    ):
        run_manual(tmp_path, run_id="prod-manual-macro", config_path=config_path)


def test_production_live_mode_rejects_file_backed_krx_inputs(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "default.yaml"
    _write_production_config(config_path)
    live_macro = MacroLoadResult(
        channel_states=dict(DEFAULT_CHANNEL_STATES),
        source_name="ecos_kosis_fred_live",
    )

    with patch("macro_screener.pipeline.runner._resolve_macro_states", return_value=live_macro):
        with pytest.raises(
            RuntimeError,
            match="krx_live_source_required_in_production_live_mode:taxonomy_only",
        ):
            run_manual(tmp_path, run_id="prod-krx-guard", config_path=config_path)


def test_production_live_mode_rejects_demo_backed_dart_inputs(tmp_path: Path) -> None:
    config_path = tmp_path / "config" / "default.yaml"
    _write_production_config(config_path)
    live_macro = MacroLoadResult(
        channel_states=dict(DEFAULT_CHANNEL_STATES),
        source_name="ecos_kosis_fred_live",
    )
    live_stocks = KRXLoadResult(
        rows=[
            {
                "stock_code": "005930",
                "stock_name": "Samsung Electronics",
                "industry_code": "제조__전자__반도체",
            }
        ],
        source="live",
        warnings=[],
    )
    demo_dart = DARTLoadResult(
        disclosures=[],
        warnings=["dart_source_unconfigured_using_demo_fallback"],
        watermark="2026-03-21T18:00:00+09:00",
        source="demo",
    )

    with patch("macro_screener.pipeline.runner._resolve_macro_states", return_value=live_macro):
        with patch(
            "macro_screener.pipeline.runner.KRXClient.load_stocks_result",
            return_value=live_stocks,
        ):
            with patch(
                "macro_screener.pipeline.runner._load_disclosures",
                return_value=demo_dart,
            ):
                with pytest.raises(
                    RuntimeError,
                    match="dart_live_source_required_in_production_live_mode:demo",
                ):
                    run_manual(tmp_path, run_id="prod-dart-guard", config_path=config_path)
