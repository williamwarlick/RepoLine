from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from model_stream import infer_access_policy, normalize_provider
from repoline_skill import (
    DEFAULT_REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    resolve_repoline_skill_prompt,
)
from voice_behavior import (
    DEFAULT_THINKING_CUE_INTERVAL_MS,
    DEFAULT_THINKING_CUE_PRESET,
    DEFAULT_THINKING_CUE_VOLUME,
    clamp_thinking_cue_interval_ms,
    clamp_thinking_cue_volume,
    resolve_thinking_cue_preset,
)

DEFAULT_CURSOR_MODEL = "composer-2-fast"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    agent_name: str
    greeting: str
    provider: str
    provider_transport: str | None
    provider_submit_mode: str | None
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
    stt_provider: str
    stt_model: str
    stt_language: str
    turn_endpointing_mode: str
    turn_min_endpointing_delay_seconds: float
    turn_max_endpointing_delay_seconds: float
    turn_interruption_mode: str
    false_interruption_timeout_seconds: float
    resume_false_interruption: bool
    tts_provider: str
    tts_model: str
    tts_voice: str
    thinking_sound_preset: str
    thinking_sound_interval_ms: int
    thinking_sound_volume: float
    thinking_sound_sip_only: bool

    @classmethod
    def load(
        cls, env: Mapping[str, str], repo_root: str | Path
    ) -> BridgeConfig:
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
        stt_provider = _resolve_stt_provider(env)
        tts_provider = _resolve_tts_provider(env)

        return cls(
            agent_name=env.get("LIVEKIT_AGENT_NAME", "clawdbot-agent"),
            greeting=env.get(
                "BRIDGE_GREETING",
                "RepoLine is live. What do you want to work on?",
            ),
            provider=provider,
            provider_transport=_resolve_provider_transport(env, provider),
            provider_submit_mode=_resolve_provider_submit_mode(env, provider),
            skill_name=skill_name,
            tts_pronunciation_skill_name=tts_pronunciation_skill_name,
            chunk_chars=int(env.get("BRIDGE_CHUNK_CHARS", "80")),
            model=_resolve_bridge_model(env, provider),
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
                env.get("FINAL_TRANSCRIPT_DEBOUNCE_SECONDS", "0.35")
            ),
            short_transcript_word_threshold=int(
                env.get("BRIDGE_SHORT_TRANSCRIPT_WORDS", "2")
            ),
            short_transcript_debounce_seconds=float(
                env.get("BRIDGE_SHORT_TRANSCRIPT_DEBOUNCE_SECONDS", "0.55")
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
            stt_provider=stt_provider,
            stt_model=_resolve_stt_model(env, stt_provider),
            stt_language=env.get("LIVEKIT_STT_LANGUAGE", "multi"),
            turn_endpointing_mode=env.get(
                "LIVEKIT_TURN_ENDPOINTING_MODE", "dynamic"
            ),
            turn_min_endpointing_delay_seconds=float(
                env.get("LIVEKIT_TURN_MIN_ENDPOINTING_DELAY_SECONDS", "0.35")
            ),
            turn_max_endpointing_delay_seconds=float(
                env.get("LIVEKIT_TURN_MAX_ENDPOINTING_DELAY_SECONDS", "1.4")
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
            tts_provider=tts_provider,
            tts_model=_resolve_tts_model(env, tts_provider),
            tts_voice=_resolve_tts_voice(env, tts_provider),
            thinking_sound_preset=_resolve_thinking_sound_preset(env),
            thinking_sound_interval_ms=_resolve_thinking_sound_interval_ms(env),
            thinking_sound_volume=_resolve_thinking_sound_volume(env),
            thinking_sound_sip_only=_env_bool(
                env, "BRIDGE_THINKING_SOUND_SIP_ONLY", True
            ),
        )


def render_call_greeting(config: BridgeConfig) -> str:
    provider_name = _provider_display_name(config.provider, config.provider_transport)
    model_name = _spoken_model_name(config.model)
    intro = f"You're talking with {model_name} through {provider_name}."
    greeting = config.greeting.strip()
    if not greeting:
        return intro
    return f"{intro} {greeting}"


def _require_env(env: Mapping[str, str], name: str) -> str:
    return env[name]


def _provider_display_name(provider: str, transport: str | None = None) -> str:
    if provider == "claude":
        return "Claude Code"
    if provider == "codex":
        return "Codex CLI"
    if provider == "cursor":
        if transport == "app":
            return "Cursor App"
        return "Cursor Agent"
    if provider == "gemini":
        return "Gemini CLI"
    return provider


def _spoken_model_name(model: str | None) -> str:
    if model is None or not model.strip():
        return "the default model"
    return model.replace("-", " ").replace("_", " ").strip()


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


def _resolve_thinking_sound_preset(env: Mapping[str, str]) -> str:
    return resolve_thinking_cue_preset(
        _env_optional(env, "BRIDGE_THINKING_SOUND_PRESET"),
        DEFAULT_THINKING_CUE_PRESET,
    )


def _resolve_thinking_sound_interval_ms(env: Mapping[str, str]) -> int:
    raw = _env_optional(env, "BRIDGE_THINKING_SOUND_INTERVAL_MS")
    if raw is None:
        return DEFAULT_THINKING_CUE_INTERVAL_MS
    return clamp_thinking_cue_interval_ms(float(raw))


def _resolve_thinking_sound_volume(env: Mapping[str, str]) -> float:
    raw = _env_optional(env, "BRIDGE_THINKING_SOUND_VOLUME")
    if raw is None:
        return DEFAULT_THINKING_CUE_VOLUME
    return clamp_thinking_cue_volume(float(raw))


def _resolve_bridge_model(
    env: Mapping[str, str], provider: str
) -> str | None:
    explicit_model = _env_optional(env, "BRIDGE_MODEL")
    if explicit_model is not None:
        return explicit_model
    if provider == "cursor":
        return DEFAULT_CURSOR_MODEL
    if provider == "gemini":
        return DEFAULT_GEMINI_MODEL
    return None


def _resolve_provider_transport(env: Mapping[str, str], provider: str) -> str | None:
    if provider == "cursor":
        value = _env_optional(env, "BRIDGE_CURSOR_TRANSPORT")
        if value is None:
            return "cli"
        normalized = value.lower()
        if normalized not in {"app", "cli"}:
            raise ValueError(
                "BRIDGE_CURSOR_TRANSPORT must be one of: app, cli"
            )
        return normalized

    if provider != "gemini":
        return None

    return "cli"


def _resolve_provider_submit_mode(
    env: Mapping[str, str], provider: str
) -> str | None:
    if provider != "cursor":
        return None

    value = _env_optional(env, "BRIDGE_CURSOR_APP_SUBMIT_MODE")
    if value is None:
        return None

    normalized = value.lower()
    if normalized not in {
        "auto",
        "active-input",
        "bridge-composer-handle",
        "bridge-submit",
    }:
        raise ValueError(
            "BRIDGE_CURSOR_APP_SUBMIT_MODE must be one of: "
            "auto, active-input, bridge-composer-handle, bridge-submit"
        )
    return normalized


def _normalize_provider_backend(
    value: str | None, *, default: str, supported: set[str]
) -> str:
    if value is None:
        return default
    normalized = value.strip().lower()
    aliases = {
        "inference": "livekit",
        "livekit-inference": "livekit",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in supported:
        supported_values = ", ".join(sorted(supported))
        raise ValueError(
            f"Unsupported provider backend '{value}'. Expected one of: {supported_values}"
        )
    return normalized


def _resolve_stt_provider(env: Mapping[str, str]) -> str:
    explicit = _env_optional(env, "BRIDGE_STT_PROVIDER")
    default = "deepgram" if _env_optional(env, "DEEPGRAM_API_KEY") else "livekit"
    provider = _normalize_provider_backend(
        explicit,
        default=default,
        supported={"deepgram", "livekit"},
    )
    if provider == "deepgram" and _env_optional(env, "DEEPGRAM_API_KEY") is None:
        raise ValueError(
            "DEEPGRAM_API_KEY is required when BRIDGE_STT_PROVIDER=deepgram"
        )
    return provider


def _resolve_tts_provider(env: Mapping[str, str]) -> str:
    explicit = _env_optional(env, "BRIDGE_TTS_PROVIDER")
    default = "elevenlabs" if _env_optional(env, "ELEVENLABS_API_KEY") else "livekit"
    provider = _normalize_provider_backend(
        explicit,
        default=default,
        supported={"elevenlabs", "livekit"},
    )
    if provider == "elevenlabs" and _env_optional(env, "ELEVENLABS_API_KEY") is None:
        raise ValueError(
            "ELEVENLABS_API_KEY is required when BRIDGE_TTS_PROVIDER=elevenlabs"
        )
    return provider


def _resolve_stt_model(env: Mapping[str, str], provider: str) -> str:
    if provider == "deepgram":
        return env.get("DEEPGRAM_STT_MODEL", "nova-3")
    return env.get("LIVEKIT_STT_MODEL", "deepgram/nova-3")


def _resolve_tts_model(env: Mapping[str, str], provider: str) -> str:
    if provider == "elevenlabs":
        return env.get("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")
    return env.get("LIVEKIT_TTS_MODEL", "cartesia/sonic-3")


def _resolve_tts_voice(env: Mapping[str, str], provider: str) -> str:
    if provider == "elevenlabs":
        voice_id = _env_optional(env, "ELEVENLABS_VOICE_ID")
        if voice_id is None:
            raise ValueError(
                "ELEVENLABS_VOICE_ID is required when BRIDGE_TTS_PROVIDER=elevenlabs"
            )
        return voice_id

    return env.get(
        "LIVEKIT_TTS_VOICE",
        "9626c31c-bec5-4cca-baa8-f8ba9e84c8bc",
    )
