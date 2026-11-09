r"""Backend for vocab-trainer.html: serves the page, translates text, reads text aloud.

Run:  .venv\Scripts\python app.py   then open http://127.0.0.1:5000
"""
import io
import json
import os
import re
import sys
import threading
from functools import lru_cache
from pathlib import Path

import onnxruntime as ort
import soundfile as sf
from flask import Flask, jsonify, request, send_file, send_from_directory
from kokoro_onnx import Kokoro

# CTranslate2's CUDA build needs cublas64_12, installed by pip under nvidia/*/bin
for d in (Path(sys.prefix) / "Lib" / "site-packages" / "nvidia").glob("*/bin"):
    os.environ["PATH"] = str(d) + os.pathsep + os.environ["PATH"]
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")  # no "PyTorch not found" notice
import ctranslate2
from transformers import AutoTokenizer

HERE = Path(__file__).resolve().parent               # tts_app: the model files live here
ROOT = HERE.parent                                   # the English folder
PAGE_FILES = {"dictionary.js"}                       # files the page may load
PASSAGES_FILE = ROOT / "passages.jsonl"              # one passage per line (git-friendly)

KOKORO_MODEL = str(HERE / "kokoro-v1.0.onnx")
KOKORO_VOICES = str(HERE / "voices-v1.0.bin")
MT_MODEL = str(HERE / "vinai-en2vi-ct2")            # vinai/vinai-translate-en2vi-v2, CTranslate2 int8
VOICE = "af_heart"                                   # e.g. bf_emma for British
MAX_CHARS = 2000

app = Flask(__name__)


def load_kokoro():
    """Kokoro on the GPU (CUDA) when there is one, otherwise on the CPU."""
    try:
        ort.preload_dlls()                           # finds the CUDA libs installed by pip
    except Exception:
        pass
    options = ort.SessionOptions()
    options.log_severity_level = 3                   # hide the noisy GPU warnings
    # HEURISTIC: the default exhaustive search re-tunes for every new sentence length (slow)
    cuda = ("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"})
    try:
        if "CUDAExecutionProvider" not in ort.get_available_providers():
            raise RuntimeError("no CUDA build of onnxruntime")
        session = ort.InferenceSession(KOKORO_MODEL, options,
                                       providers=[cuda, "CPUExecutionProvider"])
    except Exception as e:                           # no NVIDIA GPU / CUDA DLLs missing
        print("CUDA unavailable, using CPU:", e)
        session = ort.InferenceSession(KOKORO_MODEL, options,
                                       providers=["CPUExecutionProvider"])
    print("Kokoro running on", session.get_providers()[0].replace("ExecutionProvider", ""))
    return Kokoro.from_session(session, KOKORO_VOICES)


def load_translator():
    """VinAI Translate on the GPU (int8 weights, fp16 maths) when there is one, otherwise the CPU."""
    try:
        if not ctranslate2.get_cuda_device_count():
            raise RuntimeError("no CUDA device")
        model = ctranslate2.Translator(MT_MODEL, device="cuda", compute_type="int8_float16")
    except Exception as e:
        print("CUDA unavailable for the translator, using CPU:", e)
        model = ctranslate2.Translator(MT_MODEL, device="cpu", compute_type="int8")
    print("Translator running on", model.device.upper())
    return model, AutoTokenizer.from_pretrained(MT_MODEL, src_lang="en_XX")


kokoro = load_kokoro()
translator, mt_tokenizer = load_translator()           # ctranslate2.Translator is thread-safe


# ---------- page ----------
@app.get("/")
def index():
    return send_from_directory(ROOT, "vocab-trainer.html")


@app.get("/favicon.ico")
def favicon():
    return "", 204


@app.get("/<name>")
def page_file(name):
    if name not in PAGE_FILES:
        return "", 404
    return send_from_directory(ROOT, name)


# ---------- reading passages (passages.jsonl) ----------
def read_passages():
    with PASSAGES_FILE.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


@app.get("/api/passages")
def list_passages():
    return jsonify(read_passages())


@app.delete("/api/passages/<pid>")
def delete_passage(pid):
    kept = [p for p in read_passages() if p["id"] != pid]
    tmp = PASSAGES_FILE.with_suffix(".tmp")
    lines = [json.dumps(p, ensure_ascii=False) + "\n" for p in kept]
    tmp.write_text("".join(lines), encoding="utf-8", newline="\n")
    tmp.replace(PASSAGES_FILE)
    return "", 204


# ---------- translation (English -> Vietnamese, VinAI Translate runs locally) ----------
# The model was trained on single sentences, so a passage is split and translated as one batch.
SENTENCE_END = re.compile(r'(?<=[.!?])["”’)]*\s+(?=["“‘(]?[A-Z0-9])')


@lru_cache(maxsize=500)
def translate(text):
    lines = [line.strip() for line in text.splitlines()]
    pieces = [[s for s in SENTENCE_END.split(line) if s.strip()] for line in lines]
    flat = [s for line in pieces for s in line]
    if not flat:
        return ""
    src = [mt_tokenizer.convert_ids_to_tokens(mt_tokenizer.encode(s)) for s in flat]
    # vi_VN starts the decoder; CTranslate2 leaves this prefix out of the result
    results = translator.translate_batch(src, target_prefix=[["vi_VN"]] * len(src), beam_size=5)
    out = iter(mt_tokenizer.decode(mt_tokenizer.convert_tokens_to_ids(r.hypotheses[0]),
                                   skip_special_tokens=True).strip() for r in results)
    return "\n".join(" ".join(next(out) for _ in line) for line in pieces)


@app.post("/translate")
def translate_route():
    text = request.json["text"].strip()
    if len(text) > MAX_CHARS:
        return jsonify(error="Selection too long (max %d characters)." % MAX_CHARS), 400
    return jsonify(text=translate(text))


# ---------- text to speech (Kokoro, runs locally) ----------
@lru_cache(maxsize=500)
def synthesize(text):
    samples, rate = kokoro.create(text, voice=VOICE, speed=1.0, lang="en-us")
    wav = io.BytesIO()
    sf.write(wav, samples, rate, format="WAV")
    return wav.getvalue()


@app.get("/speak")
def speak_route():
    text = request.args.get("text", "").strip()[:MAX_CHARS]
    if not text:
        return "", 400
    return send_file(io.BytesIO(synthesize(text)), mimetype="audio/wav")


def warm_up():
    """Run each model once at start-up so the first click in the browser is not slow."""
    translate("hello")
    print("Translator ready", flush=True)
    synthesize("hello")                              # also tunes the GPU kernels
    print("Voice ready", flush=True)


if __name__ == "__main__":
    threading.Thread(target=warm_up, daemon=True).start()
    app.run(port=5000)
