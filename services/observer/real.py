"""Real inference remains behind the same offline OCI stdin/stdout boundary."""

import asyncio
import json
from pathlib import Path

from packages.contracts.observer import checksum
from packages.contracts.observer_real import (
    REAL_GPU_PROFILE,
    REAL_MODEL,
    REAL_PROFILE,
    WEIGHTS_HASH,
)
from services.observer.isolated import IsolatedProvider
from services.observer.prompt import PROMPT
from services.observer.provider import Identity


class RealIsolatedProvider(IsolatedProvider):
    def check_returncode(self, code: int | None) -> None:
        if code == 124:
            raise TimeoutError("observer_internal_timeout")
        super().check_returncode(code)

    def __init__(self, docker: Path | None, image: str, *, gpu: bool = False) -> None:
        super().__init__(docker, image)
        self.gpu = gpu
        self.identity = Identity("oci-local", REAL_MODEL, "sha256:" + WEIGHTS_HASH, image)

    def arguments(self, name: str) -> list[str]:
        substitutions = {
            "--memory=128m": "--memory=7g",
            "--cpus=1": "--cpus=6",
            "--pids-limit=32": "--pids-limit=128",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=4m": "--tmpfs=/tmp:rw,noexec,nosuid,size=64m",
        }
        args = [substitutions.get(arg, arg) for arg in super().arguments(name)]
        args[-1:-1] = ["--memory-swap=7g"]
        if self.gpu:
            args[-1:-1] = ["--gpus", "device=0"]
        return args

    async def verify_image(self, env: dict[str, str], directory: str) -> None:
        if self.docker is None:
            raise FileNotFoundError("observer_runtime_unavailable")
        process = await asyncio.create_subprocess_exec(
            str(self.docker),
            "image",
            "inspect",
            self.image,
            "--format",
            "{{json .Config.Labels}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
            env=env,
            cwd=directory,
        )
        try:
            assert process.stdout
            raw = bytearray()
            while chunk := await process.stdout.read(1024):
                raw.extend(chunk)
                if len(raw) > 8192:
                    raise RuntimeError("observer_image_metadata_invalid")
            if len(raw) > 8192:
                raise RuntimeError("observer_image_metadata_invalid")
            await process.wait()
            if process.returncode:
                raise FileNotFoundError("observer_image_unavailable")
            labels = json.loads(raw)
            expected = {
                "observer.model": REAL_MODEL,
                "observer.weights": WEIGHTS_HASH,
                "observer.prompt": checksum(PROMPT),
                "observer.profile": REAL_GPU_PROFILE if self.gpu else REAL_PROFILE,
            }
            if not isinstance(labels, dict) or any(labels.get(k) != v for k, v in expected.items()):
                raise RuntimeError("observer_image_identity_mismatch")
        finally:
            if process.returncode is None:
                process.kill()
                await process.wait()
