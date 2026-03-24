from __future__ import annotations

from pathlib import Path

_SRC_PACKAGE_DIR = Path(__file__).resolve().parent.parent / "src" / "macro_screener"
_SRC_INIT = _SRC_PACKAGE_DIR / "__init__.py"

if not _SRC_INIT.exists():
    raise ModuleNotFoundError(f"Unable to locate source package at {_SRC_INIT}")

__path__ = [str(_SRC_PACKAGE_DIR)]
__file__ = str(_SRC_INIT)

exec(compile(_SRC_INIT.read_text(encoding="utf-8"), __file__, "exec"))
