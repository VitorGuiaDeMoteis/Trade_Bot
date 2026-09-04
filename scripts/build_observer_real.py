"""Explicit offline build from the one approved local model and already-pulled runtimes."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from packages.contracts.observer import AIObserverOutput, checksum
from packages.contracts.observer_real import MANIFEST_HASH, REAL_GPU_PROFILE, REAL_PROFILE
from services.observer.prompt import PROMPT


def verify(path: Path, digest: str, size: int | None = None) -> None:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular_model_file_required")
    with path.open("rb") as stream:
        actual = hashlib.file_digest(stream, "sha256").hexdigest()
    if actual != digest or (size is not None and path.stat().st_size != size):
        raise ValueError("model_hash_mismatch")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--models", type=Path, required=True, help="Operator's existing model store"
    )
    parser.add_argument("--gpu", action="store_true", help="Requires verified device-0 passthrough")
    args = parser.parse_args()
    source = args.models.resolve(strict=True)
    manifest_name = Path("manifests/registry.ollama.ai/library/deepseek-r1/8b")
    verify(source / manifest_name, MANIFEST_HASH)
    manifest = json.loads((source / manifest_name).read_bytes())
    items = [manifest["config"], *manifest["layers"]]
    for item in items:
        verify(
            source / "blobs" / item["digest"].replace(":", "-"), item["digest"][7:], item["size"]
        )
    # Context is generated outside the repo. Only these allowlisted artifacts are copied.
    with tempfile.TemporaryDirectory(prefix="m5-real-context-") as directory:
        context = Path(directory).resolve()
        assert context.is_relative_to(Path(tempfile.gettempdir()).resolve())
        target = context / "models" / manifest_name
        target.parent.mkdir(parents=True)
        shutil.copyfile(source / manifest_name, target)
        (context / "models/blobs").mkdir()
        for item in items:
            relative = Path("blobs") / item["digest"].replace(":", "-")
            target = context / "models" / relative
            shutil.copyfile(source / relative, target)
            verify(target, item["digest"][7:], item["size"])
        for name in ("worker.py", "Dockerfile"):
            shutil.copyfile(Path("infrastructure/observer_real") / name, context / name)
        (context / "prompt.txt").write_text(PROMPT, encoding="utf-8", newline="\n")
        (context / "profile.json").write_text(json.dumps({"gpu": args.gpu}), encoding="utf-8")
        (context / "output.schema.json").write_text(
            json.dumps(AIObserverOutput.model_json_schema()), encoding="utf-8"
        )
        docker = shutil.which("docker")
        if docker is None:
            raise FileNotFoundError("docker_unavailable")
        # Resolve installed image IDs locally, without looking up the Python stage remotely.
        env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
        env.update(DOCKER_BUILDKIT="0", DOCKER_CONFIG=directory)
        env["DOCKER_HOST"] = (
            "npipe:////./pipe/dockerDesktopLinuxEngine"
            if os.name == "nt"
            else "unix:///var/run/docker.sock"
        )
        subprocess.run(
            [
                docker,
                "build",
                "--pull=false",
                "--network=none",
                "--build-arg",
                "PROMPT_HASH=" + checksum(PROMPT),
                "--build-arg",
                "RESOURCE_PROFILE=" + (REAL_GPU_PROFILE if args.gpu else REAL_PROFILE),
                "-t",
                "trading-bot-observer-real:1",
                str(context),
            ],
            env=env,
            check=True,
        )


if __name__ == "__main__":
    main()
