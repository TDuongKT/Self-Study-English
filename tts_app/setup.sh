#!/usr/bin/env bash
# One-shot setup: installs whatever is missing (Python, VC++ runtime, curl), then the venv,
# the libraries and the model files.   Run:  bash setup.sh   (on Windows: double-click setup.bat)
set -e
cd "$(dirname "$0")"

PY_VER=3.12.10                                      # installed when no Python 3.10-3.12 is found
case "$(uname -s)" in MINGW*|MSYS*|CYGWIN*) OS=windows ;; Darwin) OS=mac ;; *) OS=linux ;; esac
TMP_DL="$(mktemp -d)"
trap 'rm -rf "$TMP_DL"' EXIT

say() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }

# Linux: install system packages with apt / dnf / pacman (asks for the sudo password)
sys_install() {
    if command -v apt-get >/dev/null 2>&1; then sudo apt-get update && sudo apt-get install -y "$@"
    elif command -v dnf >/dev/null 2>&1; then sudo dnf install -y "$@"
    elif command -v pacman >/dev/null 2>&1; then sudo pacman -S --noconfirm "$@"
    else die "Please install these packages yourself: $*"; fi
}

# ---------- curl (downloads below) ----------
if ! command -v curl >/dev/null 2>&1; then
    say "Installing curl"
    [ "$OS" = linux ] && sys_install curl || die "curl is missing - please install it."
fi

# ---------- Python 3.10-3.12 (the versions every library here has wheels for) ----------
py_ok() { "$@" -c 'import sys, venv; sys.exit(not (3, 10) <= sys.version_info[:2] <= (3, 12))' >/dev/null 2>&1; }

# Sets the array PY to the first suitable interpreter (an array: "py -3.12" is two words and
# the per-user install path may contain spaces)
find_python() {
    local c
    # "py -3.x" is the Windows launcher; plain "python" may be the Microsoft Store stub (fails py_ok)
    for c in "py -3.12" "py -3.11" "py -3.10" python3.12 python3.11 python3.10 python3 python; do
        read -ra PY <<< "$c"
        py_ok "${PY[@]}" && return 0
    done
    if [ "$OS" = windows ] && [ -n "$LOCALAPPDATA" ]; then   # just installed, not on PATH yet
        PY=("$(cygpath -u "$LOCALAPPDATA")/Programs/Python/Python312/python.exe")
        py_ok "${PY[@]}" && return 0
    fi
    return 1
}

if ! find_python; then
    say "Python 3.10-3.12 not found - installing Python $PY_VER"
    case "$OS" in
    windows)
        # per-user install: no administrator rights needed
        curl -fL -o "$TMP_DL/python.exe" "https://www.python.org/ftp/python/$PY_VER/python-$PY_VER-amd64.exe"
        MSYS2_ARG_CONV_EXCL='*' "$TMP_DL/python.exe" /quiet InstallAllUsers=0 PrependPath=1 \
            Include_launcher=1 Include_test=0 ;;
    mac)
        command -v brew >/dev/null 2>&1 ||
            die "Install Homebrew (https://brew.sh) or Python 3.12 (https://www.python.org/downloads/), then run this again."
        brew install python@3.12 ;;
    linux)
        sys_install python3 python3-venv python3-pip ;;
    esac
    find_python || die "Python 3.10-3.12 is still not available. Install Python 3.12 (https://www.python.org/downloads/), open a new terminal and run this again."
fi
echo "Using Python: ${PY[*]} ($("${PY[@]}" -c 'import sys; print(sys.version.split()[0])'))"
[ "$OS" = linux ] && ! "${PY[@]}" -c 'import ensurepip' >/dev/null 2>&1 && sys_install python3-venv

# ---------- Windows: Visual C++ runtime (onnxruntime and ctranslate2 need msvcp140.dll) ----------
if [ "$OS" = windows ] && [ ! -f "$(cygpath -u "${SYSTEMROOT:-C:\\Windows}")/System32/msvcp140.dll" ]; then
    say "Installing the Microsoft Visual C++ runtime (Windows will ask for permission)"
    curl -fL -o "$TMP_DL/vc_redist.x64.exe" https://aka.ms/vs/17/release/vc_redist.x64.exe
    powershell -NoProfile -Command "Start-Process -Wait -Verb RunAs -FilePath '$(cygpath -w "$TMP_DL/vc_redist.x64.exe")' -ArgumentList '/install','/quiet','/norestart'" ||
        die "The Visual C++ runtime was not installed. Run this again and click Yes on the Windows prompt."
fi

# ---------- venv ----------
if [ -x .venv/Scripts/python.exe ]; then VPY=.venv/Scripts/python.exe; else VPY=.venv/bin/python; fi
# Recreate the venv if it is missing, broken (its base Python was removed) or on another Python version
if ! py_ok "$VPY"; then
    say "Creating the virtual environment"
    rm -rf .venv
    "${PY[@]}" -m venv .venv
    if [ -x .venv/Scripts/python.exe ]; then VPY=.venv/Scripts/python.exe; else VPY=.venv/bin/python; fi
fi
$VPY -m pip install --upgrade pip

# ---------- libraries ----------
# CUDA build only when an NVIDIA GPU (with its driver) is present, otherwise the CPU build
if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
    say "NVIDIA GPU found - installing the CUDA builds"
    ORT='onnxruntime-gpu[cuda,cudnn]'; CUDA12='nvidia-cuda-runtime-cu12 nvidia-cublas-cu12'
else
    say "No NVIDIA GPU found - installing the CPU builds"
    ORT='onnxruntime'; CUDA12=''
fi
$VPY -m pip uninstall -y onnxruntime onnxruntime-gpu >/dev/null 2>&1 || true
# ctranslate2 runs the translator; transformers is only used for its tokenizer (no torch needed)
$VPY -m pip install flask soundfile kokoro-onnx "$ORT" $CUDA12 \
    ctranslate2 "transformers<5" sentencepiece protobuf
# kokoro-onnx pulls in the CPU onnxruntime, which shadows the GPU build -> drop it, reinstall GPU
if [ "$ORT" != onnxruntime ]; then
    $VPY -m pip uninstall -y onnxruntime
    $VPY -m pip install --force-reinstall --no-deps onnxruntime-gpu
fi

# ---------- model files ----------
U=https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0
[ -f kokoro-v1.0.onnx ] || { say "Downloading the Kokoro voice model"; curl -fL -O "$U/kokoro-v1.0.onnx"; }
[ -f voices-v1.0.bin ]  || curl -fL -O "$U/voices-v1.0.bin"

# VinAI Translate en->vi, converted once to CTranslate2 int8. The converter needs torch, so it
# runs in a throw-away venv (short path: torch's files break Windows' 260-character path limit)
MT=vinai-en2vi-ct2
if [ ! -f "$MT/model.bin" ]; then
    say "Downloading and converting the VinAI translation model (one-off, a few minutes)"
    CV="$HOME/.ct2conv"
    rm -rf "$CV"; "${PY[@]}" -m venv "$CV"
    if [ -x "$CV/Scripts/python.exe" ]; then CPY="$CV/Scripts/python.exe"; else CPY="$CV/bin/python"; fi
    "$CPY" -m pip install --index-url https://download.pytorch.org/whl/cpu torch
    "$CPY" -m pip install ctranslate2 "transformers<5" sentencepiece protobuf
    "$CPY" -m ctranslate2.converters.transformers --model vinai/vinai-translate-en2vi-v2 \
        --output_dir "$MT" --quantization int8_float16 --force
    "$CPY" -c "from transformers import AutoTokenizer as T; T.from_pretrained('vinai/vinai-translate-en2vi-v2', src_lang='en_XX').save_pretrained('$MT')"
    rm -rf "$CV"
fi

say "Done. Start with:  $VPY app.py   then open http://127.0.0.1:5000"
