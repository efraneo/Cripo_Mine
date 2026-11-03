from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from .config import DATA_DIR, ensure_directories
from .schema import BotState


def save_state(state: BotState, path: Path | None = None) -> Path:
    ensure_directories()
    target = path or DATA_DIR / "state.json"
    target.write_text(json.dumps(asdict(state), ensure_ascii=True, indent=2), encoding="utf-8")
    return target


def load_state(path: Path | None = None) -> BotState:
    ensure_directories()
    target = path or DATA_DIR / "state.json"
    if not target.exists():
        return BotState()
    data = json.loads(target.read_text(encoding="utf-8"))
    return BotState(
        poster=data.get("poster", {}),
        hallazgos=data.get("hallazgos", []),
        acciones=data.get("acciones", []),
        five_why=data.get("five_why", []),
        guided_mode=data.get("guided_mode", True),
    )
