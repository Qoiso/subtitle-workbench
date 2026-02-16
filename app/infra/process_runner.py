from __future__ import annotations

import asyncio
from collections.abc import Callable


class ProcessRunner:
    async def run(
        self,
        cmd: list[str],
        progress_parser: Callable[[str], dict] | None = None,
        progress_cb: Callable[[dict], None] | None = None,
        on_start: Callable[[asyncio.subprocess.Process], None] | None = None,
    ) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            stdin=asyncio.subprocess.PIPE,
        )
        if on_start:
            on_start(proc)
        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        async def read_stream(stream, sink: list[str], parse: bool = False) -> None:
            while True:
                line = await stream.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                sink.append(text)
                if parse and progress_parser and progress_cb:
                    payload = progress_parser(text)
                    if payload:
                        progress_cb(payload)

        try:
            await asyncio.gather(
                read_stream(proc.stdout, stdout_chunks, False),
                read_stream(proc.stderr, stderr_chunks, True),
            )
            code = await proc.wait()
        except asyncio.CancelledError:
            if proc.returncode is None:
                proc.terminate()
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
            raise
        return code, "".join(stdout_chunks), "".join(stderr_chunks)
