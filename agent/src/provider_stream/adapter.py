from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from .claude import ClaudeProviderStreamAdapter
from .codex import CodexProviderStreamAdapter
from .common import (
    TextStreamConfig,
    TextStreamError,
    TextStreamEvent,
    TextStreamProvider,
    normalize_provider,
    provider_display_name,
)
from .cursor import CursorProviderStreamAdapter
from .runner import ProcessRunner, SubprocessProcessRunner


class ProviderStreamAdapter(Protocol):
    provider: TextStreamProvider

    def build_command(self, config: TextStreamConfig) -> list[str]: ...

    async def stream(
        self, config: TextStreamConfig, runner: ProcessRunner
    ) -> AsyncIterator[TextStreamEvent]: ...


_ADAPTERS: dict[TextStreamProvider, ProviderStreamAdapter] = {
    "claude": ClaudeProviderStreamAdapter(),
    "codex": CodexProviderStreamAdapter(),
    "cursor": CursorProviderStreamAdapter(),
}


def get_provider_adapter(
    provider: TextStreamProvider | str | None,
) -> ProviderStreamAdapter:
    return _ADAPTERS[normalize_provider(provider)]


def build_stream_command(config: TextStreamConfig) -> list[str]:
    return get_provider_adapter(config.provider).build_command(config)


async def stream_text_events(
    config: TextStreamConfig,
    runner: ProcessRunner | None = None,
) -> AsyncIterator[TextStreamEvent]:
    active_runner = runner or SubprocessProcessRunner()
    adapter = get_provider_adapter(config.provider)
    async for event in adapter.stream(config, active_runner):
        yield event


async def stream_text_chunks(
    config: TextStreamConfig,
    runner: ProcessRunner | None = None,
) -> AsyncIterator[str]:
    saw_text = False
    error_message: str | None = None

    async for event in stream_text_events(config, runner=runner):
        if event.type == "speech_chunk" and event.text:
            saw_text = True
            yield event.text
            continue

        if event.type == "error":
            error_message = (
                event.message or f"{provider_display_name(config.provider)} failed."
            )
            break

    if error_message:
        if saw_text:
            return
        raise TextStreamError(error_message)

    if not saw_text:
        raise TextStreamError(
            f"{provider_display_name(config.provider)} finished without producing speech text."
        )
