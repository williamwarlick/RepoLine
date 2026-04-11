from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from typing import Protocol


class JsonlProcess(Protocol):
    @property
    def returncode(self) -> int | None: ...

    async def iter_lines(self) -> AsyncIterator[str]: ...

    async def wait(self) -> int: ...

    def terminate(self) -> None: ...

    def kill(self) -> None: ...


class ProcessRunner(Protocol):
    async def spawn_jsonl(
        self, cmd: list[str], working_directory: str | None
    ) -> JsonlProcess: ...


class SubprocessJsonlProcess:
    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self._proc = proc

    @property
    def returncode(self) -> int | None:
        return self._proc.returncode

    async def iter_lines(self) -> AsyncIterator[str]:
        assert self._proc.stdout is not None
        async for raw_line in self._proc.stdout:
            yield raw_line.decode("utf-8", errors="replace").rstrip("\n")

    async def wait(self) -> int:
        return await self._proc.wait()

    def terminate(self) -> None:
        self._proc.terminate()

    def kill(self) -> None:
        self._proc.kill()


class SubprocessProcessRunner:
    async def spawn_jsonl(
        self, cmd: list[str], working_directory: str | None
    ) -> JsonlProcess:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            stdin=asyncio.subprocess.DEVNULL,
            cwd=working_directory or None,
            env=os.environ.copy(),
        )
        return SubprocessJsonlProcess(proc)


async def terminate_process(proc: JsonlProcess) -> None:
    if proc.returncode is not None:
        return

    proc.terminate()
    try:
        await asyncio.wait_for(proc.wait(), timeout=2)
        return
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
