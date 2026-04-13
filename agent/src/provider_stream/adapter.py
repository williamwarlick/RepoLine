from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
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

RunnerFactory = Callable[[], ProcessRunner]


class ProviderStreamAdapter(Protocol):
    provider: TextStreamProvider

    def build_command(self, config: TextStreamConfig) -> list[str]: ...

    async def stream(
        self, config: TextStreamConfig, runner: ProcessRunner
    ) -> AsyncIterator[TextStreamEvent]: ...


DEFAULT_ADAPTERS: dict[TextStreamProvider, ProviderStreamAdapter] = {
    "claude": ClaudeProviderStreamAdapter(),
    "codex": CodexProviderStreamAdapter(),
    "cursor": CursorProviderStreamAdapter(),
}


class ProviderStreamFacade:
    def __init__(
        self,
        *,
        adapters: Mapping[TextStreamProvider, ProviderStreamAdapter] | None = None,
        runner_factory: RunnerFactory = SubprocessProcessRunner,
    ) -> None:
        self._adapters = dict(adapters or DEFAULT_ADAPTERS)
        self._runner_factory = runner_factory

    def get_adapter(
        self, provider: TextStreamProvider | str | None
    ) -> ProviderStreamAdapter:
        normalized = normalize_provider(provider)
        try:
            return self._adapters[normalized]
        except KeyError as exc:
            raise ValueError(f"unsupported bridge provider: {provider}") from exc

    def build_command(self, config: TextStreamConfig) -> list[str]:
        return self.get_adapter(config.provider).build_command(config)

    async def events(
        self,
        config: TextStreamConfig,
        runner: ProcessRunner | None = None,
    ) -> AsyncIterator[TextStreamEvent]:
        active_runner = runner or self._runner_factory()
        adapter = self.get_adapter(config.provider)
        async for event in adapter.stream(config, active_runner):
            yield event

    async def chunks(
        self,
        config: TextStreamConfig,
        runner: ProcessRunner | None = None,
    ) -> AsyncIterator[str]:
        saw_text = False
        error_message: str | None = None

        async for event in self.events(config, runner=runner):
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


DEFAULT_PROVIDER_STREAM_FACADE = ProviderStreamFacade()


def get_provider_adapter(
    provider: TextStreamProvider | str | None,
) -> ProviderStreamAdapter:
    return DEFAULT_PROVIDER_STREAM_FACADE.get_adapter(provider)


def build_stream_command(config: TextStreamConfig) -> list[str]:
    return DEFAULT_PROVIDER_STREAM_FACADE.build_command(config)


async def stream_text_events(
    config: TextStreamConfig,
    runner: ProcessRunner | None = None,
) -> AsyncIterator[TextStreamEvent]:
    async for event in DEFAULT_PROVIDER_STREAM_FACADE.events(config, runner=runner):
        yield event


async def stream_text_chunks(
    config: TextStreamConfig,
    runner: ProcessRunner | None = None,
) -> AsyncIterator[str]:
    async for chunk in DEFAULT_PROVIDER_STREAM_FACADE.chunks(config, runner=runner):
        yield chunk
