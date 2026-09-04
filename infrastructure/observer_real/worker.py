"""Trusted stdio bridge to an internal offline Ollama; never interprets model commands."""

import hashlib
import http.client
import json
import subprocess
import sys
import time
from pathlib import Path

MODEL = "deepseek-r1:8b"
MANIFEST = "6995872bfe4c521a67b32da386cd21d5c6e819b6e0d62f79f64ec83be99f5763"
MAX_INPUT = 65536
MAX_OUTPUT = 16384
MAX_ENVELOPE = 131072
CONTEXT = 16384
TOKENS = 1024
GPU_TOKENS = 8192
GPU_CONTEXT = 32768
TIMEOUT = 880
ROOT = Path("/opt/observer")


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_key")
        result[key] = value
    return result


def strict(raw):
    return json.loads(
        raw.decode("utf-8"),
        object_pairs_hook=unique,
        parse_constant=lambda _: (_ for _ in ()).throw(ValueError("constant")),
    )


def request(method, path, data=None):
    # Literal endpoint; http.client never reads proxy env, follows redirects or executes tools.
    if (method, path) not in {("GET", "/api/tags"), ("POST", "/api/chat")}:
        raise ValueError("endpoint")
    conn = http.client.HTTPConnection("127.0.0.1", 11434, timeout=TIMEOUT)
    try:
        body = json.dumps(data, ensure_ascii=False).encode() if data is not None else None
        conn.request(method, path, body=body, headers={"Content-Type": "application/json"})
        response = conn.getresponse()
        if response.status != 200:
            raise ValueError("http")
        raw = response.read(MAX_ENVELOPE + 1)
        if len(raw) > MAX_ENVELOPE:
            raise ValueError("envelope_size")
        return strict(raw)
    finally:
        conn.close()


def payload(snapshot, prompt, schema, *, gpu=False):
    # No dynamic endpoint, model, options, tools or system prompt from snapshot.
    strict(snapshot)
    return {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": snapshot.decode("utf-8")},
        ],
        "format": schema,
        "stream": False,
        "think": gpu,
        "keep_alive": 0,
        "options": {
            "temperature": 0,
            "seed": 0,
            "num_ctx": GPU_CONTEXT if gpu else CONTEXT,
            "num_predict": GPU_TOKENS if gpu else TOKENS,
            "num_batch": 128,
            "num_thread": 6,
            "num_gpu": -1 if gpu else 0,
        },
    }


def extract(envelope, *, gpu=False):
    tokens = GPU_TOKENS if gpu else TOKENS
    context = GPU_CONTEXT if gpu else CONTEXT
    if (
        envelope.get("model") != MODEL
        or envelope.get("done") is not True
        or envelope.get("done_reason") != "stop"
        or not 0 < envelope.get("prompt_eval_count", 0) < context - tokens - 256
        or not 0 < envelope.get("eval_count", 0) <= tokens
    ):
        raise ValueError("incomplete_or_context_limit")
    message = envelope["message"]
    if message.get("tool_calls"):
        raise ValueError("tools_forbidden")
    content = message["content"]
    if not isinstance(content, str):
        raise ValueError("content")
    raw = content.encode("utf-8")
    if len(raw) > MAX_OUTPUT:
        raise ValueError("output_size")
    if not isinstance(strict(raw), dict):
        raise ValueError("document")
    # The separate runtime thinking field is never returned or persisted.
    # Do not strip prefix/suffix, markdown or <think>; strict JSON must already hold.
    return raw


def verify_blobs():
    manifest = ROOT / "models/manifests/registry.ollama.ai/library/deepseek-r1/8b"
    raw = manifest.read_bytes()
    if hashlib.sha256(raw).hexdigest() != MANIFEST:
        raise ValueError("manifest")
    value = strict(raw)
    for item in [value["config"], *value["layers"]]:
        digest = item["digest"]
        if not digest.startswith("sha256:") or len(digest) != 71:
            raise ValueError("digest")
        blob = ROOT / "models/blobs" / digest.replace(":", "-")
        with blob.open("rb") as stream:
            actual = hashlib.file_digest(stream, "sha256").hexdigest()
        if blob.stat().st_size != item["size"] or actual != digest[7:]:
            raise ValueError("blob")


def main():
    snapshot = sys.stdin.buffer.read(MAX_INPUT + 1)
    if len(snapshot) > MAX_INPUT:
        raise ValueError("input_size")
    verify_blobs()
    prompt = (ROOT / "prompt.txt").read_text(encoding="utf-8")
    schema = strict((ROOT / "output.schema.json").read_bytes())
    gpu = strict((ROOT / "profile.json").read_bytes())["gpu"]
    if type(gpu) is not bool:
        raise ValueError("invalid_profile")
    env = {
        "HOME": "/tmp",
        "PATH": "/usr/bin:/bin",
        "OLLAMA_HOST": "127.0.0.1:11434",
        "OLLAMA_MODELS": str(ROOT / "models"),
        "OLLAMA_NO_CLOUD": "1",
        "OLLAMA_NUM_PARALLEL": "1",
        "OLLAMA_MAX_LOADED_MODELS": "1",
        "OLLAMA_FLASH_ATTENTION": "1",
        "OLLAMA_KV_CACHE_TYPE": "q8_0",
        "OLLAMA_CONTEXT_LENGTH": str(GPU_CONTEXT if gpu else CONTEXT),
        "OLLAMA_KEEP_ALIVE": "0",
        "OLLAMA_LOAD_TIMEOUT": "10m",
        "CUDA_VISIBLE_DEVICES": "0" if gpu else "-1",
    }
    process = subprocess.Popen(
        ["/bin/ollama", "serve"],
        env=env,
        cwd="/tmp",
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                tags = request("GET", "/api/tags")
                break
            except (OSError, ValueError):
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("startup_failed") from None
                time.sleep(0.1)
        selected = [x for x in tags["models"] if x["name"] == MODEL]
        if len(selected) != 1 or selected[0]["digest"] != MANIFEST:
            raise ValueError("model_unavailable")
        answer = extract(
            request("POST", "/api/chat", payload(snapshot, prompt, schema, gpu=gpu)), gpu=gpu
        )
        sys.stdout.buffer.write(answer)
    finally:
        process.terminate()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


if __name__ == "__main__":
    try:
        main()
    except TimeoutError:
        sys.exit(124)
    except Exception:
        # Parent records controlled MODEL_ERROR/HOLD; no response, reasoning or log escapes.
        sys.exit(1)
