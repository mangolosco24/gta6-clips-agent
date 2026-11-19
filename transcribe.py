"""Word-level transcript of the clip with faster-whisper (CPU, runs locally, free)."""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
MODELS = os.environ.get("WHISPER_DIR") or os.path.join(HERE, "models")
MODEL_SIZE = os.environ.get("WHISPER_MODEL", "small")


def ensure_model():
    from faster_whisper import WhisperModel
    return WhisperModel(MODEL_SIZE, device="cpu", compute_type="int8", download_root=MODELS)


def words(video, cache):
    """[{"w", "start", "end"}] relative to the clip start; cached in `cache`."""
    if os.path.exists(cache):
        return json.load(open(cache, encoding="utf-8"))
    model = ensure_model()
    segs, _ = model.transcribe(video, language="en", word_timestamps=True, vad_filter=True,
                               condition_on_previous_text=False)
    out = [{"w": w.word.strip(), "start": round(w.start, 2), "end": round(w.end, 2)}
           for s in segs for w in (s.words or []) if w.word.strip()]
    json.dump(out, open(cache, "w", encoding="utf-8"), indent=0, ensure_ascii=False)
    return out


if __name__ == "__main__":
    ensure_model()
    print(f"whisper model '{MODEL_SIZE}' ready in {MODELS}")
