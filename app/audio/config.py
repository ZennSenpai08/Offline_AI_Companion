from dataclasses import asdict, dataclass, fields
import math


@dataclass(frozen=True)
class AudioSettings:
    consent: bool = False
    auto_listen: bool = False
    device: str = ""  # host API + device name, never an unstable numeric index
    model_path: str = ""
    language: str = "auto"
    sensitivity: float = 1.0
    vad_mode: int = 2
    silence_ms: int = 600
    minimum_ms: int = 240
    maximum_seconds: int = 25
    threads: int = 4
    preview: bool = True

    @classmethod
    def parse(cls, value):
        if isinstance(value, cls):
            value = asdict(value)
        if not isinstance(value, dict) or set(value) - {f.name for f in fields(cls)}:
            raise ValueError("Invalid audio settings fields.")
        result = cls(**value)
        for name in ("consent", "auto_listen", "preview"):
            if type(getattr(result, name)) is not bool:
                raise ValueError(f"Audio {name} must be a boolean.")
        for name, limit in (("device", 1024), ("model_path", 4096)):
            if not isinstance(getattr(result, name), str) or len(getattr(result, name)) > limit:
                raise ValueError(f"Invalid audio {name}.")
        if result.language not in ("auto", "en", "tl"):
            raise ValueError("Recognition language must be auto, en or tl.")
        if type(result.sensitivity) not in (int, float) or not math.isfinite(result.sensitivity) or not .25 <= result.sensitivity <= 4:
            raise ValueError("Microphone sensitivity must be 0.25–4.")
        for name, low, high in (("vad_mode", 0, 3), ("silence_ms", 200, 2000),
                                ("minimum_ms", 100, 1000), ("maximum_seconds", 2, 25), ("threads", 1, 8)):
            number = getattr(result, name)
            if type(number) is not int or not low <= number <= high:
                raise ValueError(f"Audio {name} must be {low}–{high}.")
        return result
