from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from macro_screener.config import load_config
from macro_screener.config.loader import load_env_file


def test_default_config_loads(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    project_root = tmp_path / "project"
    config_dir = project_root / "config"
    config_dir.mkdir(parents=True)
    (config_dir / "default.yaml").write_text(
        """
config_version: "custom"
stage1:
  manual_channel_states:
    G: 1
    IC: 0
    FC: -1
    ED: 0
    FX: 1
        """.strip(),
        encoding="utf-8",
    )
    monkeypatch.chdir(project_root)

    config = load_config()

    assert config.config_version == "custom"
    assert config.stage1.manual_channel_states["G"] == 1
    assert config.stage1.rank_table_artifact_path == "config/stage1_sector_rank_tables.v1.json"
    assert config.schedule.pre_open_time == "08:30"


def test_missing_config_uses_repo_defaults(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.stage2.decay_half_lives["governance_risk"] == 120
    assert config.universe.industry_master_path == "data/reference/industry_master.csv"
    assert config.universe.markets == ("KOSPI", "KOSDAQ")
    assert config.runtime.normal_mode == "live"
    assert config.runtime.ecos_api_key_env == "ECOS_API_KEY"
    assert config.runtime.fred_api_key_env == "FRED_API_KEY"
    assert config.runtime.kosis_api_key_env == "KOSIS_API_KEY"
    assert config.runtime.krx_api_key_env == "KRX_API_KEY"
    assert config.runtime.allow_manual_macro_states_in_live_mode is False
    assert config.runtime.allow_local_file_inputs_in_live_mode is False


def test_show_config_cli_uses_custom_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "custom.yaml"
        config_path.write_text(
            """
config_version: "cli-custom"
schedule:
  pre_open_time: "08:45"
paths:
  latest_snapshot_pointer: "custom/latest.json"
            """.strip(),
            encoding="utf-8",
        )

        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2] / "src")
        completed = subprocess.run(
            [
                "python3",
                "-m",
                "macro_screener.cli",
                "show-config",
                "--config",
                str(config_path),
            ],
            check=True,
            capture_output=True,
            text=True,
            env=env,
        )

        payload = json.loads(completed.stdout)
        assert payload["config_version"] == "cli-custom"
        assert payload["schedule"]["pre_open_time"] == "08:45"
        assert payload["paths"]["latest_snapshot_pointer"] == "custom/latest.json"


def test_load_env_file_parses_spaced_assignments(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        """
DART_API_KEY = test-dart
export ECOS_API_KEY = "test-ecos"
FRED_API_KEY='test-fred'
KOSIS_API_KEY = test-kosis
        """.strip(),
        encoding="utf-8",
    )
    for key in ("DART_API_KEY", "ECOS_API_KEY", "FRED_API_KEY", "KOSIS_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    load_env_file(env_path)

    assert os.environ["DART_API_KEY"] == "test-dart"
    assert os.environ["ECOS_API_KEY"] == "test-ecos"
    assert os.environ["FRED_API_KEY"] == "test-fred"
    assert os.environ["KOSIS_API_KEY"] == "test-kosis"
