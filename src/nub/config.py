"""
Configuration for Nub.

All tunable parameters in one place. Loaded from:
1. Defaults (this file)
2. Config file (~/.config/nub/config.toml) if exists
3. Environment variables (NUB_*) override file
4. CLI flags override everything
"""

from __future__ import annotations

import contextlib
import os
import tomllib  # stdlib in 3.11+
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class WeightsConfig:
    """Importance scoring weights for S = w_p*P + w_g*G + w_t*T"""
    positional: float = 0.3
    grep: float = 1.0
    topology: float = 0.5


@dataclass
class CompressionConfig:
    """Core compression settings."""
    default_budget: int = 2000
    min_line_chars: int = 160  # below this, fold rather than show useless fragments
    temperature: float = 0.5  # lower = more aggressive concentration on high-scoring items
    deduplicate_ngrams: bool = False  # remove repeated 3-word sequences


@dataclass
class TextConfig:
    """Text format topology scores."""
    section_score: float = 0.6
    line_score: float = 0.5


@dataclass
class IOConfig:
    """File I/O settings for large file handling."""
    max_file_size: int = 1 * 1024 * 1024  # 1MB threshold for head+tail
    head_bytes: int = 500 * 1024  # 500KB from start
    tail_bytes: int = 500 * 1024  # 500KB from end


@dataclass
class Config:
    """Root config with all settings."""
    weights: WeightsConfig = field(default_factory=WeightsConfig)
    compression: CompressionConfig = field(default_factory=CompressionConfig)
    text: TextConfig = field(default_factory=TextConfig)
    io: IOConfig = field(default_factory=IOConfig)


def get_config_path() -> Path:
    """Get config file path, respecting XDG."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return Path(xdg) / "nub" / "config.toml"
    return Path.home() / ".config" / "nub" / "config.toml"


def load_config() -> Config:
    """Load config from file if exists, else return defaults."""
    config = Config()
    path = get_config_path()

    if path.exists():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            config = _apply_toml(config, data)
        except Exception:
            pass  # fall back to defaults on any error

    # env var overrides
    config = _apply_env(config)

    return config


def _apply_toml(config: Config, data: dict) -> Config:
    """Apply toml data to config."""
    if "weights" in data:
        w = data["weights"]
        if "positional" in w:
            config.weights.positional = float(w["positional"])
        if "grep" in w:
            config.weights.grep = float(w["grep"])
        if "topology" in w:
            config.weights.topology = float(w["topology"])

    if "compression" in data:
        c = data["compression"]
        if "default_budget" in c:
            config.compression.default_budget = int(c["default_budget"])
        if "min_line_chars" in c:
            config.compression.min_line_chars = int(c["min_line_chars"])
        if "temperature" in c:
            config.compression.temperature = float(c["temperature"])
        if "deduplicate_ngrams" in c:
            config.compression.deduplicate_ngrams = bool(c["deduplicate_ngrams"])

    if "text" in data:
        t = data["text"]
        if "section_score" in t:
            config.text.section_score = float(t["section_score"])
        if "line_score" in t:
            config.text.line_score = float(t["line_score"])

    if "io" in data:
        io = data["io"]
        if "max_file_size" in io:
            config.io.max_file_size = int(io["max_file_size"])
        if "head_bytes" in io:
            config.io.head_bytes = int(io["head_bytes"])
        if "tail_bytes" in io:
            config.io.tail_bytes = int(io["tail_bytes"])

    return config


def _apply_env(config: Config) -> Config:
    """Apply environment variable overrides."""
    env_map: dict[str, tuple[str, str, type]] = {
        "NUB_W_POSITIONAL": ("weights", "positional", float),
        "NUB_W_GREP": ("weights", "grep", float),
        "NUB_W_TOPOLOGY": ("weights", "topology", float),
        "NUB_DEFAULT_BUDGET": ("compression", "default_budget", int),
        "NUB_MIN_LINE_CHARS": ("compression", "min_line_chars", int),
        "NUB_TEMPERATURE": ("compression", "temperature", float),
        "NUB_DEDUPLICATE": ("compression", "deduplicate_ngrams", bool),
        "NUB_TEXT_SECTION_SCORE": ("text", "section_score", float),
        "NUB_TEXT_LINE_SCORE": ("text", "line_score", float),
        "NUB_MAX_FILE_SIZE": ("io", "max_file_size", int),
        "NUB_HEAD_BYTES": ("io", "head_bytes", int),
        "NUB_TAIL_BYTES": ("io", "tail_bytes", int),
    }

    for env_key, (section, attr, conv) in env_map.items():
        val = os.environ.get(env_key)
        if val is not None:
            with contextlib.suppress(ValueError, AttributeError):
                # Bool needs special handling: "true", "1", "yes" -> True
                converted = val.lower() in ("true", "1", "yes") if conv is bool else conv(val)
                setattr(getattr(config, section), attr, converted)

    return config


# Module-level config instance, loaded once on import
_config: Config | None = None


def get_config() -> Config:
    """Get the global config instance."""
    global _config
    if _config is None:
        _config = load_config()
    return _config
