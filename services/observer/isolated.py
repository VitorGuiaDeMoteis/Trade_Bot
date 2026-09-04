"""OCI stdio boundary. No host subprocess is used to run model code."""

import asyncio
import os
import re
import tempfile
from pathlib import Path
from uuid import uuid4

from packages.contracts.observer import MAX_INPUT_BYTES, MAX_OUTPUT_BYTES
from services.observer.prompt import PROMPT
from services.observer.provider import Identity


class IsolatedProvider:
    def __init__(self, docker: Path | None, image: str) -> None:
        if (docker is not None and not docker.is_absolute()) or not re.fullmatch(
            r"sha256:[a-f0-9]{64}", image
        ):
            raise ValueError("observer_absolute_runtime_and_image_digest_required")
        self.docker, self.image = docker, image
        self.identity = Identity("docker", "local-observer", image)

    def arguments(self, name: str) -> list[str]:
        if self.docker is None:
            raise FileNotFoundError("observer_runtime_unavailable")
        return [
            str(self.docker),
            "run",
            "--pull=never",
            "--rm",
            "--interactive",
            "--name",
            name,
            "--network=none",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges",
            "--pids-limit=32",
            "--memory=128m",
            "--cpus=1",
            "--user=65534:65534",
            "--workdir=/tmp",
            "--tmpfs=/tmp:rw,noexec,nosuid,size=4m",
            "--env=LANG=C.UTF-8",
            "--env=TZ=UTC",
            self.image,
        ]

    async def generate(self, snapshot: bytes, prompt: str) -> bytes:
        if len(snapshot) > MAX_INPUT_BYTES or prompt != PROMPT:
            raise ValueError("observer_transport_contract")
        name = f"observer-{uuid4().hex}"
        with tempfile.TemporaryDirectory(prefix="observer-") as directory:
            # Only the trusted Docker client runs on the host. No inherited config/context/helpers.
            env = {key: os.environ[key] for key in ("SystemRoot", "WINDIR") if key in os.environ}
            env["DOCKER_CONFIG"] = directory
            if os.name == "nt":
                env["DOCKER_HOST"] = "npipe:////./pipe/dockerDesktopLinuxEngine"
            else:
                env["DOCKER_HOST"] = "unix:///var/run/docker.sock"
            process = await asyncio.create_subprocess_exec(
                *self.arguments(name),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=directory,
                env=env,
            )
            assert process.stdin and process.stdout and process.stderr

            async def read(stream: asyncio.StreamReader, limit: int, keep: bool) -> bytes:
                buffer = bytearray()
                count = 0
                while chunk := await stream.read(4096):
                    count += len(chunk)
                    if count > limit:
                        raise ValueError("observer_output_limit")
                    if keep:
                        buffer.extend(chunk)
                return bytes(buffer)

            async def send() -> None:
                assert process.stdin
                process.stdin.write(snapshot)
                await process.stdin.drain()
                process.stdin.close()

            try:
                async with asyncio.TaskGroup() as group:
                    output = group.create_task(read(process.stdout, MAX_OUTPUT_BYTES, True))
                    group.create_task(read(process.stderr, 4096, False))
                    group.create_task(send())
                    group.create_task(process.wait())
                if process.returncode != 0:
                    raise RuntimeError("observer_process_failed")
                return output.result()
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()
                # Kill only this invocation's container, including timeout/oversized-output paths.
                cleanup = await asyncio.create_subprocess_exec(
                    str(self.docker),
                    "rm",
                    "--force",
                    name,
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                    cwd=directory,
                    env=env,
                )
                try:
                    await asyncio.wait_for(cleanup.wait(), timeout=3)
                except TimeoutError:
                    cleanup.kill()
                    await cleanup.wait()
                    raise RuntimeError("observer_cleanup_failed") from None
