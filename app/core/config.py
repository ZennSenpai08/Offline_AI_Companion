from __future__ import annotations

from dataclasses import asdict, dataclass, fields, field
from app.audio.config import AudioSettings
import json
import math
import os
from pathlib import Path
import tempfile


class ConfigError(ValueError):
    """Invalid configuration must be preserved, never silently overwritten."""


@dataclass
class Settings:
    version: int = 1
    x: int | None = None
    y: int | None = None
    screen_name: str = ""
    work_area: list[int] | None = None
    scale: float = 1.0
    always_on_top: bool = True
    flipped: bool = False
    animation_enabled: bool = True
    animation_fps: int = 30
    animation_intensity: float = 1.0
    reduced_motion: bool = False
    audio: AudioSettings = field(default_factory=AudioSettings)
    # Click-through intentionally starts OFF after every restart.

    @classmethod
    def parse(cls, data: object) -> Settings:
        if not isinstance(data, dict):
            raise ConfigError("Settings must be a JSON object.")
        allowed = {field.name for field in fields(cls)}
        if set(data) - allowed:
            raise ConfigError("Unknown settings fields; use a compatible application version.")
        result = cls(**data)
        try:
            result.audio = AudioSettings.parse(result.audio)
        except (ValueError, TypeError) as exc:
            raise ConfigError(str(exc)) from exc
        if type(result.version) is not int or result.version != 1:
            raise ConfigError("Unsupported settings version.")
        if (result.x is None) != (result.y is None):
            raise ConfigError("Position requires both x and y.")
        for value in (result.x, result.y):
            if value is not None and (type(value) is not int or abs(value) > 1_000_000):
                raise ConfigError("Invalid desktop coordinates.")
        if type(result.scale) not in (int, float) or not math.isfinite(result.scale) or not 0.5 <= result.scale <= 2.0:
            raise ConfigError("Character scale must be between 0.5 and 2.0.")
        if not isinstance(result.screen_name, str) or len(result.screen_name) > 256:
            raise ConfigError("Invalid monitor identity.")
        if type(result.always_on_top) is not bool or type(result.flipped) is not bool:
            raise ConfigError("Window preferences must be booleans.")
        if type(result.animation_enabled) is not bool or type(result.reduced_motion) is not bool:
            raise ConfigError("Animation preferences must be booleans.")
        if type(result.animation_fps) is not int or result.animation_fps not in (30, 60):
            raise ConfigError("Animation FPS must be 30 or 60.")
        if type(result.animation_intensity) not in (int, float) or not math.isfinite(result.animation_intensity) or not 0 <= result.animation_intensity <= 1.5:
            raise ConfigError("Animation intensity must be between 0 and 1.5.")
        if result.work_area is not None:
            area = result.work_area
            if not isinstance(area, list) or len(area) != 4 or any(type(v) is not int or abs(v) > 1_000_000 for v in area):
                raise ConfigError("Invalid saved monitor work area.")
            if area[2] <= 0 or area[3] <= 0:
                raise ConfigError("Monitor work area must have positive dimensions.")
        return result


class SettingsStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.path = directory / "settings.json"

    def load(self) -> Settings:
        if not self.path.exists():
            return Settings()
        try:
            if self.path.stat().st_size > 65536:
                raise ConfigError("Settings file is too large.")
            return Settings.parse(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, UnicodeError, ValueError, TypeError) as exc:
            raise ConfigError(f"Cannot read {self.path}: {exc}. Preserve or rename this file before restarting.") from exc

    def save(self, settings: Settings) -> None:
        data = asdict(settings)
        Settings.parse(data)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=self.directory, prefix="settings-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                json.dump(data, stream, indent=2, allow_nan=False)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
