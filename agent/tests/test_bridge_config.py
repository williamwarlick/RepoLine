from __future__ import annotations

from pathlib import Path

import pytest

from bridge_config import BridgeConfig, render_call_greeting


def _install_skill(workdir: Path, provider: str, skill_name: str) -> None:
    if provider == "cursor":
        path = workdir / ".cursor" / "rules" / f"{skill_name}.mdc"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            """---
description: RepoLine voice session behavior
alwaysApply: true
---

# RepoLine Voice Session
""",
            encoding="utf-8",
        )
        return

    root = ".claude" if provider == "claude" else ".agents"
    path = workdir / root / "skills" / skill_name / "SKILL.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""---
name: {skill_name}
description: Example
---

Use short spoken replies.
""",
        encoding="utf-8",
    )


def _base_env(workdir: Path, **overrides: str) -> dict[str, str]:
    env = {
        "BRIDGE_CLI_PROVIDER": "claude",
        "BRIDGE_WORKDIR": str(workdir),
        "REPOLINE_SKILL_NAME": "repoline-voice-session",
        "REPOLINE_TTS_PRONUNCIATION_SKILL_NAME": "repoline-tts-pronunciation",
        "LIVEKIT_API_KEY": "key",
        "LIVEKIT_API_SECRET": "secret",
        "LIVEKIT_URL": "wss://example.livekit.cloud",
    }
    env.update(overrides)
    return env


def test_bridge_config_load_normalizes_provider_and_access_policy(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "cursor", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="cursor-agent",
            BRIDGE_ACCESS_POLICY="write",
        ),
        repo_root=tmp_path,
    )

    assert config.provider == "cursor"
    assert config.access_policy == "workspace-write"
    assert "RepoLine voice rule" in config.system_prompt


def test_bridge_config_load_uses_legacy_codex_flags_when_policy_is_missing(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "codex", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="codex",
            CODEX_DANGEROUSLY_BYPASS_APPROVALS_AND_SANDBOX="true",
        ),
        repo_root=tmp_path,
    )

    assert config.provider == "codex"
    assert config.access_policy == "owner"
    assert config.thinking_level == "low"


def test_bridge_config_load_supports_reasoning_effort_alias(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "codex", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="codex",
            BRIDGE_CODEX_REASONING_EFFORT="medium",
        ),
        repo_root=tmp_path,
    )

    assert config.thinking_level == "medium"


def test_bridge_config_load_disables_livekit_recording_by_default(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "claude", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(workdir),
        repo_root=tmp_path,
    )

    assert config.livekit_record_audio is False
    assert config.livekit_record_traces is False
    assert config.livekit_record_logs is False
    assert config.livekit_record_transcript is False
    assert config.thinking_sound_preset == "soft-pulse"
    assert config.thinking_sound_interval_ms == 1800
    assert config.thinking_sound_volume == pytest.approx(0.11)
    assert config.thinking_sound_sip_only is True


def test_bridge_config_load_defaults_cursor_model_to_composer_2_fast(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "cursor", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="cursor",
        ),
        repo_root=tmp_path,
    )

    assert config.model == "composer-2-fast"
    assert config.provider_transport == "cli"
    assert config.chunk_chars == 80
    assert config.final_transcript_debounce_seconds == 0.35
    assert config.short_transcript_debounce_seconds == 0.55
    assert config.turn_min_endpointing_delay_seconds == 0.35
    assert config.turn_max_endpointing_delay_seconds == 1.4


def test_bridge_config_load_defaults_gemini_model_to_flash(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "gemini", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="gemini",
        ),
        repo_root=tmp_path,
    )

    assert config.provider == "gemini"
    assert config.provider_transport == "cli"
    assert config.model == "gemini-2.5-flash"
    assert "Use the `repoline-voice-session` skill silently" in config.system_prompt


def test_bridge_config_load_supports_gemini_api_transport(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "gemini", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="gemini",
            BRIDGE_GEMINI_TRANSPORT="api",
        ),
        repo_root=tmp_path,
    )

    assert config.provider == "gemini"
    assert config.provider_transport == "api"


def test_bridge_config_load_supports_thinking_sound_overrides(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "claude", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_THINKING_SOUND_PRESET="glass",
            BRIDGE_THINKING_SOUND_INTERVAL_MS="0",
            BRIDGE_THINKING_SOUND_VOLUME="0.22",
            BRIDGE_THINKING_SOUND_SIP_ONLY="false",
        ),
        repo_root=tmp_path,
    )

    assert config.thinking_sound_preset == "glass"
    assert config.thinking_sound_interval_ms == 0
    assert config.thinking_sound_volume == pytest.approx(0.22)
    assert config.thinking_sound_sip_only is False


def test_render_call_greeting_announces_model_and_provider(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "gemini", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="gemini",
        ),
        repo_root=tmp_path,
    )

    assert (
        render_call_greeting(config)
        == "You're talking with gemini 2.5 flash through Gemini CLI. "
        "RepoLine is live. What do you want to work on?"
    )


def test_render_call_greeting_announces_gemini_api_transport(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "gemini", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="gemini",
            BRIDGE_GEMINI_TRANSPORT="api",
        ),
        repo_root=tmp_path,
    )

    assert (
        render_call_greeting(config)
        == "You're talking with gemini 2.5 flash through Gemini API. "
        "RepoLine is live. What do you want to work on?"
    )


def test_render_call_greeting_preserves_custom_greeting(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "cursor", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="cursor",
            BRIDGE_GREETING="Tell me what you want to change.",
        ),
        repo_root=tmp_path,
    )

    assert (
        render_call_greeting(config)
        == "You're talking with composer 2 fast through Cursor Agent. "
        "Tell me what you want to change."
    )


def test_bridge_config_load_supports_cursor_app_transport(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "cursor", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="cursor",
            BRIDGE_CURSOR_TRANSPORT="app",
        ),
        repo_root=tmp_path,
    )

    assert config.provider == "cursor"
    assert config.provider_transport == "app"


def test_bridge_config_load_supports_cursor_app_submit_mode(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "cursor", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="cursor",
            BRIDGE_CURSOR_TRANSPORT="app",
            BRIDGE_CURSOR_APP_SUBMIT_MODE="bridge-composer-handle",
        ),
        repo_root=tmp_path,
    )

    assert config.provider == "cursor"
    assert config.provider_transport == "app"
    assert config.provider_submit_mode == "bridge-composer-handle"


def test_render_call_greeting_announces_cursor_app_transport(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "cursor", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_CLI_PROVIDER="cursor",
            BRIDGE_CURSOR_TRANSPORT="app",
        ),
        repo_root=tmp_path,
    )

    assert (
        render_call_greeting(config)
        == "You're talking with composer 2 fast through Cursor App. "
        "RepoLine is live. What do you want to work on?"
    )


def test_bridge_config_load_supports_direct_deepgram_and_elevenlabs(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "claude", "repoline-voice-session")

    config = BridgeConfig.load(
        _base_env(
            workdir,
            BRIDGE_STT_PROVIDER="deepgram",
            DEEPGRAM_API_KEY="deepgram-key",
            DEEPGRAM_STT_MODEL="nova-3",
            BRIDGE_TTS_PROVIDER="elevenlabs",
            ELEVENLABS_API_KEY="elevenlabs-key",
            ELEVENLABS_TTS_MODEL="eleven_flash_v2_5",
            ELEVENLABS_VOICE_ID="voice-123",
        ),
        repo_root=tmp_path,
    )

    assert config.stt_provider == "deepgram"
    assert config.stt_model == "nova-3"
    assert config.tts_provider == "elevenlabs"
    assert config.tts_model == "eleven_flash_v2_5"
    assert config.tts_voice == "voice-123"


def test_bridge_config_load_requires_direct_provider_credentials(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "claude", "repoline-voice-session")

    with pytest.raises(ValueError, match="DEEPGRAM_API_KEY"):
        BridgeConfig.load(
            _base_env(workdir, BRIDGE_STT_PROVIDER="deepgram"),
            repo_root=tmp_path,
        )

    with pytest.raises(ValueError, match="ELEVENLABS_API_KEY"):
        BridgeConfig.load(
            _base_env(workdir, BRIDGE_TTS_PROVIDER="elevenlabs"),
            repo_root=tmp_path,
        )

def test_bridge_config_load_raises_for_invalid_prometheus_port(tmp_path: Path) -> None:
    workdir = tmp_path / "repo"
    _install_skill(workdir, "claude", "repoline-voice-session")

    with pytest.raises(ValueError):
        BridgeConfig.load(
            _base_env(workdir, BRIDGE_PROMETHEUS_PORT="abc"),
            repo_root=tmp_path,
        )


def test_bridge_config_load_requires_installed_skill_without_override(
    tmp_path: Path,
) -> None:
    workdir = tmp_path / "repo"

    with pytest.raises(FileNotFoundError):
        BridgeConfig.load(
            _base_env(workdir, BRIDGE_CLI_PROVIDER="codex"),
            repo_root=tmp_path,
        )
