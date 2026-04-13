from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from model_stream import infer_access_policy, normalize_provider
from repoline_skill import (
    DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    resolve_repoline_skill_prompt,
)


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    agent_name: str
    greeting: str
    provider: str
    skill_name: str
    tts_pronunciation_skill_name: str
    chunk_chars: int
    model: str | None
    thinking_level: str | None
    system_prompt: str
    working_directory: str
    access_policy: str
    final_transcript_debounce_seconds: float
    short_transcript_word_threshold: int
    short_transcript_debounce_seconds: float
    telemetry_jsonl_path: str | None
    livekit_record_audio: bool
    livekit_record_traces: bool
    livekit_record_logs: bool
    livekit_record_transcript: bool
    prometheus_port: int | None
    stt_model: str
    stt_language: str
    turn_endpointing_mode: str
    turn_min_endpointing_delay_seconds: float
    turn_max_endpointing_delay_seconds: float
    turn_interruption_mode: str
    false_interruption_timeout_seconds: float
    resume_false_interruption: bool
    tts_model: str
    tts_voice: str

    @classmethod
    def load(
        cls, env: Mapping[str, str], repo_root: str | Path
    ) -> "BridgeConfig":
        root = Path(repo_root).expanduser()
        agent_dir = root / "agent" if (root / "agent").is_dir() else root

        provider = normalize_provider(_require_env(env, "BRIDGE_CLI_PROVIDER"))
        working_directory = _require_env(env, "BRIDGE_WORKDIR")
        skill_name = _require_env(env, "REPOLINE_SKILL_NAME")
        tts_pronunciation_skill_name = env.get(
            "REPOLINE_TTS_PRONUNCIATION_SKILL_NAME",
            DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
        )

        system_prompt = resolve_repoline_skill_prompt(
            provider=provider,
            working_directory=working_directory,
            explicit_system_prompt=env.get("BRIDGE_SYSTEM_PROMPT"),
            skill_name=skill_name,
            tts_pronunciation_skill_name=tts_pronunciation_skill_name,
        ).prompt

        return cls(
            agent_name=env.get("LIVEKIT_AGENT_NAME", "clawdbot-agent"),
            greeting=env.get(
                "BRIDGE_GREETING",
                "RepoLine is live. What do you want to work on?",
            ),
            provider=provider,
            skill_name=skill_name,
            tts_pronunciation_skill_name=tts_pronunciation_skill_name,
            chunk_chars=int(env.get("BRIDGE_CHUNK_CHARS", "140")),
            model=_env_optional(env, "BRIDGE_MODEL"),
            thinking_level=_resolve_thinking_level(env),
            system_prompt=system_prompt,
            working_directory=working_directory,
            access_policy=infer_access_policy(
                provider,
                _env_optional(env, "BRIDGE_ACCESS_POLICY"),
                legacy_codex_bypass=_env_optional_bool(
                    env, "CODEX_DANGEROUSLY_BYPASS_APPROVALS_AND_SANDBOX"
                ),
                legacy_cursor_force=_env_optional_bool(env, "BRIDGE_CURSOR_FORCE"),
                legacy_cursor_approve_mcps=_env_optional_bool(
                    env, "BRIDGE_CURSOR_APPROVE_MCPS"
                ),
                legacy_cursor_sandbox_mode=_env_optional(
                    env, "BRIDGE_CURSOR_SANDBOX"
                ),
            ),
            final_transcript_debounce_seconds=float(
                env.get("FINAL_TRANSCRIPT_DEBOUNCE_SECONDS", "0.85")
            ),
            short_transcript_word_threshold=int(
                env.get("BRIDGE_SHORT_TRANSCRIPT_WORDS", "2")
            ),
            short_transcript_debounce_seconds=float(
                env.get("BRIDGE_SHORT_TRANSCRIPT_DEBOUNCE_SECONDS", "2.75")
            ),
            telemetry_jsonl_path=env.get("BRIDGE_TELEMETRY_JSONL")
            or str(agent_dir / "logs" / "bridge-telemetry.jsonl"),
            livekit_record_audio=_env_bool(env, "LIVEKIT_RECORD_AUDIO", False),
            livekit_record_traces=_env_bool(env, "LIVEKIT_RECORD_TRACES", False),
            livekit_record_logs=_env_bool(env, "LIVEKIT_RECORD_LOGS", False),
            livekit_record_transcript=_env_bool(
                env, "LIVEKIT_RECORD_TRANSCRIPT", False
            ),
            prometheus_port=_env_int(env, "BRIDGE_PROMETHEUS_PORT"),
            stt_model=env.get("LIVEKIT_STT_MODEL", "deepgram/nova-3"),
            stt_language=env.get("LIVEKIT_STT_LANGUAGE", "multi"),
            turn_endpointing_mode=env.get(
                "LIVEKIT_TURN_ENDPOINTING_MODE", "dynamic"
            ),
            turn_min_endpointing_delay_seconds=float(
                env.get("LIVEKIT_TURN_MIN_ENDPOINTING_DELAY_SECONDS", "0.8")
            ),
            turn_max_endpointing_delay_seconds=float(
                env.get("LIVEKIT_TURN_MAX_ENDPOINTING_DELAY_SECONDS", "2.2")
            ),
            turn_interruption_mode=env.get(
                "LIVEKIT_TURN_INTERRUPTION_MODE", "adaptive"
            ),
            false_interruption_timeout_seconds=float(
                env.get("LIVEKIT_FALSE_INTERRUPTION_TIMEOUT_SECONDS", "1.5")
            ),
            resume_false_interruption=_env_bool(
                env, "LIVEKIT_RESUME_FALSE_INTERRUPTION", True
            ),
            tts_model=env.get("LIVEKIT_TTS_MODEL", "cartesia/sonic-3"),
            tts_voice=env.get(
                "LIVEKIT_TTS_VOICE",
                "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
            ),
        )


def _require_env(env: Mapping[str, str], name: str) -> str:
    return env[name]


def _env_bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    value = env.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(env: Mapping[str, str], name: str) -> int | None:
    value = env.get(name)
    if value is None or not value.strip():
        return None
    return int(value)


def _env_optional(env: Mapping[str, str], name: str) -> str | None:
    value = env.get(name)
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _env_optional_bool(env: Mapping[str, str], name: str) -> bool | None:
    value = _env_optional(env, name)
    if value is None:
        return None
    return value.lower() in {"1", "true", "yes", "on"}


def _resolve_thinking_level(env: Mapping[str, str]) -> str | None:
    return (
        _env_optional(env, "BRIDGE_THINKING_LEVEL")
        or _env_optional(env, "BRIDGE_CODEX_REASONING_EFFORT")
        or "low"
    )
