from __future__ import annotations

from pathlib import Path

import pytest

from bridge_config import BridgeConfig


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
