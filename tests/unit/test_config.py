from __future__ import annotations

from pathlib import Path

from _pytest.monkeypatch import MonkeyPatch

from macro_screener.config import load_config


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
    assert config.schedule.pre_open_time == "08:30"


def test_missing_config_uses_repo_defaults(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)

    config = load_config()

    assert config.stage2.decay_half_lives["governance_risk"] == 120
    assert config.universe.markets == ("KOSPI", "KOSDAQ")
