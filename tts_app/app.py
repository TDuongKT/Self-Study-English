r"""Backend for vocab-trainer.html: serves the page, translates text, reads text aloud.

Run:  .venv\Scripts\python app.py   then open http://127.0.0.1:5000
"""
import io
import json
import threading
from functools import lru_cache
from pathlib import Path

import onnxruntime as ort
import requests
import soundfile as sf
from flask import Flask, jsonify, request, send_file, send_from_directory
from kokoro_onnx import Kokoro

ROOT = Path(__file__).resolve().parent.parent        # the English folder
PAGE_FILES = {"dictionary.js"}                       # files the page may load
PASSAGES_FILE = ROOT / "passages.jsonl"              # one passage per line (git-friendly)

OLLAMA_URL = "http://127.0.0.1:11434/api/chat"
OLLAMA_MODEL = "maternion/hy-mt2:1.8b"
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
    session = ort.InferenceSession(
        "kokoro-v1.0.onnx", options,
        # HEURISTIC: the default exhaustive search re-tunes for every new sentence length (slow)
        providers=[("CUDAExecutionProvider", {"cudnn_conv_algo_search": "HEURISTIC"}),
                   "CPUExecutionProvider"])
    print("Kokoro running on", session.get_providers()[0].replace("ExecutionProvider", ""))
    return Kokoro.from_session(session, "voices-v1.0.bin")


kokoro = load_kokoro()


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


# ---------- translation (English -> Vietnamese, via Ollama) ----------
def ask_ollama(prompt, **options):
    res = requests.post(OLLAMA_URL, timeout=120, json={
        "model": OLLAMA_MODEL, "stream": False, "keep_alive": "30m",
        "options": options, "messages": [{"role": "user", "content": prompt}],
    })
    res.raise_for_status()
    return res.json()["message"]["content"].strip()


@lru_cache(maxsize=500)
def translate(text):
    return ask_ollama(
        "Translate the following segment into Vietnamese, without additional explanation.\n\n" + text,
        temperature=0)


@app.post("/translate")
def translate_route():
    text = request.json["text"].strip()
    if len(text) > MAX_CHARS:
        return jsonify(error="Đoạn chọn quá dài (tối đa %d ký tự)." % MAX_CHARS), 400
    try:
        return jsonify(text=translate(text))
    except requests.RequestException:
        return jsonify(error="Không kết nối được Ollama với model " + OLLAMA_MODEL), 502


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
    breakpoint()
    if not text:
        return "", 400
    return send_file(io.BytesIO(synthesize(text)), mimetype="audio/wav")


def warm_up():
    """Run each model once at start-up so the first click in the browser is not slow."""
    try:
        translate("hello")                           # loads the translation model into memory
        print("Translator ready", flush=True)
    except requests.RequestException:
        print("Translator not ready (is Ollama running?)", flush=True)
    synthesize("hello")                              # also tunes the GPU kernels
    print("Voice ready", flush=True)


if __name__ == "__main__":
    threading.Thread(target=warm_up, daemon=True).start()
    app.run(port=5000)
