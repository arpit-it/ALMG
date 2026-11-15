"""On-device Qwen inference and explicit model setup."""
import os
import platform
from concurrent.futures import ThreadPoolExecutor
from importlib.util import find_spec
from pathlib import Path

if __package__:
    from .model_setup import ModelSetup
else:
    from model_setup import ModelSetup

MODEL = "mlx-community/Qwen3.8-27B-4bit"
DIRECTORY = Path(os.environ.get("STUDIO_MODEL_DIR", Path(__file__).parent / "models" / "qwen3.8-27b")).resolve()
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="qwen")
SETUP = ModelSetup(MODEL, DIRECTORY)
_model = None
_processor = None
_loaded_stamp = None


def supported():
    """Report whether the host supports Apple silicon inference."""
    return platform.system() == "Darwin" and platform.machine() == "arm64"


def status():
    """Return model readiness, download progress, and runtime availability."""
    return {
        "model": MODEL, "directory": str(DIRECTORY), "supported": supported(),
        "runtime": find_spec("mlx_vlm") is not None, **SETUP.status(),
    }


def start_setup(action="resume"):
    """Validate and dispatch a model setup action."""
    if not supported() or find_spec("mlx_vlm") is None:
        raise ValueError("Install the MLX runtime on an Apple silicon Mac first.")
    if action not in ("pause", "resume", "verify"):
        raise ValueError("Unknown model setup action.")
    SETUP.start(action)


def _generate(messages, max_tokens, on_delta=None, stop=None):
    """Load verified model files on demand and generate text within the context budget."""
    global _model, _processor, _loaded_stamp
    from mlx_vlm import generate, load, stream_generate

    if not SETUP.status()["ready"]:
        raise ValueError("Complete model verification before chatting.")
    stamp = SETUP.read(SETUP.verified_path)
    if _model is None or stamp != _loaded_stamp:
        _model = _processor = None
        _model, _processor = load(str(DIRECTORY))
        _loaded_stamp = stamp
    tokenizer = getattr(_processor, "tokenizer", _processor)
    prompt = tokenizer.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True, enable_thinking=False,
    )
    if len(tokenizer.encode(prompt)) + max_tokens > 8192:
        raise ValueError("This conversation exceeds the local context limit. Start a new chat or shorten the input.")
    if on_delta is not None:
        chunks = []
        reason = "stop"
        if not stop.is_set():
            from contextlib import closing

            with closing(stream_generate(_model, _processor, prompt, max_tokens=max_tokens, temperature=0.0)) as stream:
                for result in stream:
                    if stop.is_set():
                        break
                    if result.text:
                        on_delta(result.text)
                        chunks.append(result.text)
                    reason = result.finish_reason or reason
        return "".join(chunks).strip(), "cancelled" if stop.is_set() else reason
    result = generate(_model, _processor, prompt, max_tokens=max_tokens, temperature=0.0, verbose=False)
    return result.text.strip()


def reply(messages, max_tokens=1024, *, on_delta=None, stop=None):
    """Run inference on the dedicated worker and return the generated reply."""
    if not supported():
        raise ValueError("Qwen inference currently requires an Apple silicon Mac.")
    if find_spec("mlx_vlm") is None:
        raise ValueError("Install the MLX runtime from backend/requirements.txt.")
    state = status()
    if not state["ready"] or state["downloading"]:
        raise ValueError("Complete local Qwen setup in the Chat tab first.")
    return WORKER.submit(_generate, messages, max_tokens, on_delta, stop).result()
