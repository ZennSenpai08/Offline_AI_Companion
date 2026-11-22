"""One offline recognition request. Receives PCM before importing native code."""
import json
import os
import struct
import sys
import time


def main():
    # stdout is only a bounded JSON response; suppress native stdout/stderr text.
    result_fd = os.dup(sys.stdout.fileno())
    with open(os.devnull, "w") as sink:
        os.dup2(sink.fileno(), 1)
        os.dup2(sink.fileno(), 2)
    response = {"error": "Recognition worker did not complete."}
    try:
        length_data = sys.stdin.buffer.read(4)  # Parent assigns Job Object before sending anything.
        if len(length_data) != 4:
            return 2
        length = struct.unpack("<I", length_data)[0]
        if not 3200 <= length <= 800000 or length % 2:
            raise ValueError("Invalid PCM frame length.")
        pcm = sys.stdin.buffer.read(length)
        if len(pcm) != length:
            raise ValueError("Truncated PCM request.")
        from app.audio.model import verify_model
        model_path = verify_model(sys.argv[1])
        threads = int(sys.argv[2])
        language = sys.argv[3]
        if not 1 <= threads <= 8 or language not in ("auto", "en", "tl"):
            raise ValueError("Invalid recognition parameters.")
        import numpy as np
        from pywhispercpp.model import Model
        started = time.perf_counter()
        model = Model(str(model_path), n_threads=threads, language=language,
                      translate=False, no_context=True, print_progress=False,
                      print_realtime=False, print_timestamps=False,
                      context_params={"use_gpu": False}, redirect_whispercpp_logs_to=None)
        loaded = time.perf_counter()
        audio = np.frombuffer(pcm, dtype="<i2").astype(np.float32)
        audio *= 1 / 32768.0
        segments = model.transcribe(audio)
        text = " ".join(segment.text.strip() for segment in segments).strip()[:8192]
        response = {"text": text, "load_seconds": loaded - started,
                    "inference_seconds": time.perf_counter() - loaded}
    except Exception as exc:
        # Never include input PCM or decoded text in diagnostic logs.
        response = {"error": f"{type(exc).__name__}: {exc}"[:1000]}
    finally:
        with os.fdopen(result_fd, "wb") as stream:
            stream.write(json.dumps(response, ensure_ascii=True).encode("ascii"))
    return 0 if "error" not in response else 2


if __name__ == "__main__":
    raise SystemExit(main())
