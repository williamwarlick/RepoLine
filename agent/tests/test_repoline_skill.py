from repoline_skill import (
    extract_skill_body,
    resolve_repoline_skill_prompt,
)


def test_extract_skill_body_strips_frontmatter() -> None:
    markdown = """---
name: repoline-voice-session
description: Example
---

# RepoLine

Use short spoken replies.
"""

    assert extract_skill_body(markdown) == "# RepoLine\n\nUse short spoken replies."


def test_resolve_repoline_skill_prompt_prefers_installed_skill_hint_only(tmp_path) -> None:
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

Use short spoken replies.
""",
        encoding="utf-8",
    )

    fallback_skill = tmp_path / "fallback" / "SKILL.md"
    fallback_skill.parent.mkdir(parents=True)
    fallback_skill.write_text(
        """---
name: repoline-voice-session
description: Example
---

Fallback body.
""",
        encoding="utf-8",
    )

    resolved = resolve_repoline_skill_prompt(
        provider="claude",
        working_directory=workdir,
        explicit_system_prompt=None,
        default_system_prompt="Default prompt.",
        fallback_skill_markdown_path=fallback_skill,
    )

    assert resolved.mode == "installed"
    assert resolved.source_path == str(installed_skill)
    assert "Fallback body." not in resolved.prompt
    assert "RepoLine voice session" in resolved.prompt


def test_resolve_repoline_skill_prompt_falls_back_to_bundled_skill(tmp_path) -> None:
    fallback_skill = tmp_path / "skills" / "repoline-voice-session" / "SKILL.md"
    fallback_skill.parent.mkdir(parents=True)
    fallback_skill.write_text(
        """---
name: repoline-voice-session
description: Example
---

Use short spoken replies.
""",
        encoding="utf-8",
    )

    resolved = resolve_repoline_skill_prompt(
        provider="codex",
        working_directory=tmp_path / "repo",
        explicit_system_prompt=None,
        default_system_prompt="Default prompt.",
        fallback_skill_markdown_path=fallback_skill,
    )

    assert resolved.mode == "fallback-skill"
    assert resolved.source_path == str(fallback_skill)
    assert "Use short spoken replies." in resolved.prompt
    assert "RepoLine voice session" in resolved.prompt


def test_resolve_repoline_skill_prompt_respects_explicit_prompt(tmp_path) -> None:
    resolved = resolve_repoline_skill_prompt(
        provider="claude",
        working_directory=tmp_path / "repo",
        explicit_system_prompt="Speak plainly.",
        default_system_prompt="Default prompt.",
    )

    assert resolved.mode == "env-override"
    assert resolved.prompt.startswith("Speak plainly.")
    assert "RepoLine voice session" in resolved.prompt
