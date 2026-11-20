"""Load config.yaml and resolve project-relative paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PROJECT_ROOT / "config.yaml"


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Read the YAML config. Fails loudly if the file is missing or empty."""
    config_path = Path(path) if path else DEFAULT_CONFIG
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    if not isinstance(cfg, dict):
        raise ValueError(f"Config file {config_path} is empty or not a mapping")
    return cfg


def project_path(relative: str | Path) -> Path:
    """Turn a path from the config into an absolute path under the project root."""
    p = Path(relative)
    return p if p.is_absolute() else PROJECT_ROOT / p
