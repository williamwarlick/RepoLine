from __future__ import annotations

from provider_stream.adapter import (
    DEFAULT_PROVIDER_STREAM_FACADE,
    ProviderStreamAdapter,
    ProviderStreamFacade,
    build_stream_command,
    get_provider_adapter,
    stream_text_chunks,
    stream_text_events,
)
from provider_stream.common import (
    ACCESS_POLICY_ALIASES,
    AccessPolicy,
    ArtifactKind,
    SentenceChunker,
    TextStreamConfig,
    TextStreamError,
    TextStreamEvent,
    TextStreamProvider,
    UiArtifact,
    _embed_prompt_instructions,
    _extract_codex_item_artifacts,
    _extract_content_artifacts,
    _extract_embedded_code_artifacts,
    _extract_incremental_text,
    _extract_text_candidate,
    extract_text_from_content,
    infer_access_policy,
    normalize_access_policy,
    normalize_provider,
    provider_display_name,
)


def build_claude_command(config: TextStreamConfig) -> list[str]:
    return get_provider_adapter("claude").build_command(config)


def build_codex_command(config: TextStreamConfig) -> list[str]:
    return get_provider_adapter("codex").build_command(config)


def build_cursor_command(config: TextStreamConfig) -> list[str]:
    return get_provider_adapter("cursor").build_command(config)


def build_gemini_command(config: TextStreamConfig) -> list[str]:
    return get_provider_adapter("gemini").build_command(config)


__all__ = [
    "ACCESS_POLICY_ALIASES",
    "DEFAULT_PROVIDER_STREAM_FACADE",
    "AccessPolicy",
    "ArtifactKind",
    "ProviderStreamAdapter",
    "ProviderStreamFacade",
    "SentenceChunker",
    "TextStreamConfig",
    "TextStreamError",
    "TextStreamEvent",
    "TextStreamProvider",
    "UiArtifact",
    "_embed_prompt_instructions",
    "_extract_codex_item_artifacts",
    "_extract_content_artifacts",
    "_extract_embedded_code_artifacts",
    "_extract_incremental_text",
    "_extract_text_candidate",
    "build_claude_command",
    "build_codex_command",
    "build_cursor_command",
    "build_gemini_command",
    "build_stream_command",
    "extract_text_from_content",
    "get_provider_adapter",
    "infer_access_policy",
    "normalize_access_policy",
    "normalize_provider",
    "provider_display_name",
    "stream_text_chunks",
    "stream_text_events",
]
