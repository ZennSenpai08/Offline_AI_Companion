"""Read-only dependency/device diagnostic. Does not open a capture stream."""
import importlib.metadata
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main():
    errors = []
    versions = {}
    for name in ("sounddevice", "webrtcvad-wheels", "numpy", "soxr", "pywhispercpp"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            errors.append("Missing package: " + name)
    devices = []
    native_checks = {}
    backend = {}
    if not errors:
        try:
            import numpy as np
            import soxr
            import webrtcvad
            from pywhispercpp.model import Model
            import _pywhispercpp
            import sounddevice
            binary = Path(_pywhispercpp.__file__)
            backend = {"binding_path": str(binary), "binding_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
                       "binding_version": getattr(_pywhispercpp, "__version__", None),
                       "system_info": _pywhispercpp.whisper_print_system_info(),
                       "portaudio": sounddevice.get_portaudio_version(),
                       "default_input": dict(sounddevice.query_devices(kind="input"))}
            native_checks["webrtc_silence_rejected"] = not webrtcvad.Vad(2).is_speech(bytes(640), 16000)
            converted = soxr.resample(np.zeros(48000, dtype=np.int16), 48000, 16000)
            native_checks["soxr_output_samples"] = len(converted)
            native_checks["whisper_binding_has_tagalog"] = "tl" in Model.available_languages()
            if not native_checks["webrtc_silence_rejected"] or len(converted) != 16000 or not native_checks["whisper_binding_has_tagalog"]:
                errors.append("Native VAD/resampler/recognizer language self-check failed.")
            from app.audio.capture import input_devices
            devices = input_devices()
            if not devices:
                errors.append("No input devices were enumerated.")
        except Exception as exc:
            errors.append("Native import/self-check/input enumeration: " + str(exc))
    try:
        from app.audio.model import verify_model
        model = str(verify_model())
        provenance = json.loads(Path(model + ".json").read_text(encoding="utf-8"))
    except Exception as exc:
        model = None
        provenance = None
        errors.append(str(exc))
    print(json.dumps(dict(python=sys.version, executable=sys.executable, versions=versions,
                         devices=devices, native_checks=native_checks, backend=backend,
                         model=model, model_provenance=provenance, errors=errors), indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
