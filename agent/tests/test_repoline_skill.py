import pytest

from repoline_skill import resolve_repoline_skill_prompt


def test_resolve_repoline_skill_prompt_prefers_installed_skill_hint_only(
    tmp_path,
) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir(parents=True)
    (workdir / "README.md").write_text(
        "RepoLine is a voice bridge for coding agents.\n\n- supports phone and browser sessions\n",
        encoding="utf-8",
    )
    installed_skill = (
        workdir / ".claude" / "skills" / "repoline-voice-session" / "SKILL.md"
    )
    installed_skill.parent.mkdir(parents=True)
    installed_skill.write_text(
        """---
name: repoline-voice-session
description: Example
---

Use short spoken replies.
""",
        encoding="utf-8",
    )

    resolved = resolve_repoline_skill_prompt(
        provider="claude",
        working_directory=workdir,
        explicit_system_prompt=None,
    )

    assert resolved.mode == "installed"
    assert resolved.source_path == str(installed_skill)
    assert "RepoLine voice session" in resolved.prompt
    assert "live phone call or browser voice session" in resolved.prompt
    assert "Do not default to long bullet lists, numbered lists, or menu-style option dumps." in resolved.prompt
    assert "Answer from the current request, recent conversation, and repo context first" in resolved.prompt
    assert "Immediate repo context from README.md" in resolved.prompt
    assert "RepoLine is a voice bridge for coding agents." in resolved.prompt


def test_resolve_repoline_skill_prompt_respects_explicit_prompt(tmp_path) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir(parents=True)
    (workdir / "README.md").write_text(
        "RepoLine connects voice sessions to a local coding CLI.\n",
        encoding="utf-8",
    )
    resolved = resolve_repoline_skill_prompt(
        provider="claude",
        working_directory=workdir,
        explicit_system_prompt="Speak plainly.",
    )

    assert resolved.mode == "env-override"
    assert resolved.prompt.startswith("Speak plainly.")
    assert "RepoLine voice session" in resolved.prompt
    assert "Use one or two short sentences unless the user explicitly asks for structure." in resolved.prompt
    assert "Immediate repo context from README.md" in resolved.prompt


def test_resolve_repoline_skill_prompt_requires_installed_skill_without_override(
    tmp_path,
) -> None:
    with pytest.raises(FileNotFoundError):
        resolve_repoline_skill_prompt(
            provider="codex",
            working_directory=tmp_path / "repo",
            explicit_system_prompt=None,
        )


def test_resolve_repoline_skill_prompt_supports_cursor_rules(tmp_path) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir(parents=True)
    (workdir / "README.md").write_text(
        "RepoLine is a voice bridge.\n",
        encoding="utf-8",
    )
    installed_rule = workdir / ".cursor" / "rules" / "repoline-voice-session.mdc"
    installed_rule.parent.mkdir(parents=True)
    installed_rule.write_text(
        """---
description: RepoLine voice session behavior
alwaysApply: true
---

# RepoLine Voice Session
""",
        encoding="utf-8",
    )

    resolved = resolve_repoline_skill_prompt(
        provider="cursor",
        working_directory=workdir,
        explicit_system_prompt=None,
    )

    assert resolved.mode == "installed"
    assert resolved.source_path == str(installed_rule)
    assert "RepoLine voice rule" in resolved.prompt
    assert "Ask at most one concise follow-up question at a time." in resolved.prompt
    assert "If you need to inspect files or run commands" in resolved.prompt
    assert "Immediate repo context from README.md" not in resolved.prompt
    assert "live phone call or browser voice session" not in resolved.prompt


def test_resolve_repoline_skill_prompt_mentions_tts_pronunciation_skill_when_installed(
    tmp_path,
) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir(parents=True)
    (workdir / "README.md").write_text(
        "RepoLine is a voice bridge.\n",
        encoding="utf-8",
    )
    installed_skill = (
        workdir / ".claude" / "skills" / "repoline-voice-session" / "SKILL.md"
    )
    installed_tts_skill = (
        workdir / ".claude" / "skills" / "repoline-tts-pronunciation" / "SKILL.md"
    )
    installed_skill.parent.mkdir(parents=True)
    installed_tts_skill.parent.mkdir(parents=True)
    installed_skill.write_text(
        """---
name: repoline-voice-session
description: Example
---
""",
        encoding="utf-8",
    )
    installed_tts_skill.write_text(
        """---
name: repoline-tts-pronunciation
description: Example
---
""",
        encoding="utf-8",
    )

    resolved = resolve_repoline_skill_prompt(
        provider="claude",
        working_directory=workdir,
        explicit_system_prompt=None,
        tts_pronunciation_skill_name="repoline-tts-pronunciation",
    )

    assert "repoline-tts-pronunciation" in resolved.prompt
    assert "provider-specific notes" in resolved.prompt


def test_resolve_repoline_skill_prompt_omits_tts_pronunciation_hint_when_missing(
    tmp_path,
) -> None:
    workdir = tmp_path / "repo"
    workdir.mkdir(parents=True)
    (workdir / "README.md").write_text(
        "RepoLine is a voice bridge.\n",
        encoding="utf-8",
    )
    installed_skill = (
        workdir / ".claude" / "skills" / "repoline-voice-session" / "SKILL.md"
    )
    installed_skill.parent.mkdir(parents=True)
    installed_skill.write_text(
        """---
name: repoline-voice-session
description: Example
---
""",
        encoding="utf-8",
    )

    resolved = resolve_repoline_skill_prompt(
        provider="claude",
        working_directory=workdir,
        explicit_system_prompt=None,
        tts_pronunciation_skill_name="repoline-tts-pronunciation",
    )

    assert "provider-specific notes" not in resolved.prompt


def test_resolve_repoline_skill_prompt_omits_repo_context_when_readme_missing(
    tmp_path,
) -> None:
    workdir = tmp_path / "repo"
    installed_skill = (
        workdir / ".claude" / "skills" / "repoline-voice-session" / "SKILL.md"
    )
    installed_skill.parent.mkdir(parents=True)
    installed_skill.write_text(
        """---
name: repoline-voice-session
description: Example
---
""",
        encoding="utf-8",
    )

    resolved = resolve_repoline_skill_prompt(
        provider="claude",
        working_directory=workdir,
        explicit_system_prompt=None,
    )

    assert "Immediate repo context from README.md" not in resolved.prompt
