from __future__ import annotations

import json
import sqlite3

from cursor_app_tap import (
    CursorComposerTail,
    find_active_composer_id,
    list_workspace_composers,
    load_bubbles,
    search_workspace_conversations,
)


def _write_workspace_storage(tmp_path, workspace_root, composer_id: str) -> None:
    workspace_storage = (
        tmp_path / "Library" / "Application Support" / "Cursor" / "User" / "workspaceStorage" / "abc123"
    )
    workspace_storage.mkdir(parents=True)
    (workspace_storage / "workspace.json").write_text(
        json.dumps({"folder": workspace_root.as_uri()}),
        encoding="utf-8",
    )
    db_path = workspace_storage / "state.vscdb"
    connection = sqlite3.connect(db_path)
    connection.execute("create table ItemTable (key text, value blob)")
    connection.execute(
        "insert into ItemTable(key, value) values (?, ?)",
        (
            "composer.composerData",
            json.dumps(
                {
                    "selectedComposerIds": [composer_id],
                    "lastFocusedComposerIds": [composer_id],
                }
            ),
        ),
    )
    connection.commit()
    connection.close()


def _write_global_storage(
    tmp_path,
    *,
    workspace_root,
    composer_id: str,
    user_text: str,
    assistant_text: str,
    name: str | None = None,
    is_archived: bool = False,
    last_updated_at: int = 1776172927045,
) -> None:
    global_storage = (
        tmp_path / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage"
    )
    global_storage.mkdir(parents=True)
    db_path = global_storage / "state.vscdb"
    connection = sqlite3.connect(db_path)
    connection.execute("create table ItemTable (key text, value blob)")
    connection.execute("create table cursorDiskKV (key text unique on conflict replace, value blob)")
    connection.execute(
        "insert into ItemTable(key, value) values (?, ?)",
        (
            "composer.composerHeaders",
            json.dumps(
                {
                    "allComposers": [
                        {
                            "composerId": composer_id,
                            "name": name,
                            "isArchived": is_archived,
                            "lastUpdatedAt": last_updated_at,
                            "workspaceIdentifier": {
                                "uri": {"fsPath": str(workspace_root.resolve())}
                            },
                        }
                    ]
                }
            ),
        ),
    )
    connection.execute(
        "insert into cursorDiskKV(key, value) values (?, ?)",
        (
            f"composerData:{composer_id}",
            json.dumps(
                {
                    "composerId": composer_id,
                    "fullConversationHeadersOnly": [
                        {"bubbleId": "user-1", "type": 1},
                        {"bubbleId": "assistant-1", "type": 2},
                    ],
                    "status": "completed",
                }
            ),
        ),
    )
    connection.execute(
        "insert into cursorDiskKV(key, value) values (?, ?)",
        (
            f"bubbleId:{composer_id}:user-1",
            json.dumps(
                {
                    "bubbleId": "user-1",
                    "type": 1,
                    "text": user_text,
                    "createdAt": "2026-04-13T18:48:19.448Z",
                    "requestId": "request-1",
                }
            ),
        ),
    )
    connection.execute(
        "insert into cursorDiskKV(key, value) values (?, ?)",
        (
            f"bubbleId:{composer_id}:assistant-1",
            json.dumps(
                {
                    "bubbleId": "assistant-1",
                    "type": 2,
                    "text": assistant_text,
                    "createdAt": "2026-04-13T18:48:22.740Z",
                }
            ),
        ),
    )
    connection.commit()
    connection.close()


def test_find_active_composer_id_reads_workspace_selection(tmp_path) -> None:
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    _write_workspace_storage(tmp_path, workspace_root, "composer-123")
    _write_global_storage(
        tmp_path,
        workspace_root=workspace_root,
        composer_id="composer-123",
        user_text="What is RepoLine?",
        assistant_text="RepoLine is a voice bridge.",
    )

    composer_id = find_active_composer_id(
        workspace_root,
        cursor_support_dir=tmp_path / "Library" / "Application Support" / "Cursor",
    )

    assert composer_id == "composer-123"


def test_load_bubbles_reads_cursor_sqlite_payloads(tmp_path) -> None:
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    _write_workspace_storage(tmp_path, workspace_root, "composer-123")
    _write_global_storage(
        tmp_path,
        workspace_root=workspace_root,
        composer_id="composer-123",
        user_text="What is RepoLine?",
        assistant_text="RepoLine is a voice bridge.",
    )

    bubbles = load_bubbles(
        "composer-123",
        cursor_support_dir=tmp_path / "Library" / "Application Support" / "Cursor",
    )

    assert [bubble.role for bubble in bubbles] == ["user", "assistant"]
    assert bubbles[0].text == "What is RepoLine?"
    assert bubbles[1].text == "RepoLine is a voice bridge."


def test_cursor_composer_tail_emits_new_and_updated_bubbles(tmp_path) -> None:
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    _write_workspace_storage(tmp_path, workspace_root, "composer-123")
    _write_global_storage(
        tmp_path,
        workspace_root=workspace_root,
        composer_id="composer-123",
        user_text="What is RepoLine?",
        assistant_text="RepoLine is a voice bridge.",
    )
    cursor_support_dir = tmp_path / "Library" / "Application Support" / "Cursor"
    tail = CursorComposerTail("composer-123", cursor_support_dir=cursor_support_dir)

    initial_updates = tail.snapshot_updates(include_existing=True)

    assert [update.kind for update in initial_updates] == ["new", "new"]
    assert initial_updates[1].delta_text == "RepoLine is a voice bridge."

    db_path = cursor_support_dir / "User" / "globalStorage" / "state.vscdb"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "update cursorDiskKV set value = ? where key = ?",
        (
            json.dumps(
                {
                    "bubbleId": "assistant-1",
                    "type": 2,
                    "text": "RepoLine is a voice bridge for CLI coding agents.",
                    "createdAt": "2026-04-13T18:48:22.740Z",
                }
            ),
            "bubbleId:composer-123:assistant-1",
        ),
    )
    connection.commit()
    connection.close()

    updated = tail.snapshot_updates(include_existing=False)

    assert len(updated) == 1
    assert updated[0].kind == "update"
    assert updated[0].delta_text == " for CLI coding agents."


def test_cursor_composer_tail_emits_future_new_bubbles_after_initial_snapshot(
    tmp_path,
) -> None:
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    _write_workspace_storage(tmp_path, workspace_root, "composer-123")
    _write_global_storage(
        tmp_path,
        workspace_root=workspace_root,
        composer_id="composer-123",
        user_text="What is RepoLine?",
        assistant_text="RepoLine is a voice bridge.",
    )
    cursor_support_dir = tmp_path / "Library" / "Application Support" / "Cursor"
    tail = CursorComposerTail("composer-123", cursor_support_dir=cursor_support_dir)

    tail.snapshot_updates(include_existing=True)

    db_path = cursor_support_dir / "User" / "globalStorage" / "state.vscdb"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "update cursorDiskKV set value = ? where key = ?",
        (
            json.dumps(
                {
                    "composerId": "composer-123",
                    "fullConversationHeadersOnly": [
                        {"bubbleId": "user-1", "type": 1},
                        {"bubbleId": "assistant-1", "type": 2},
                        {"bubbleId": "assistant-2", "type": 2},
                    ],
                    "status": "completed",
                }
            ),
            "composerData:composer-123",
        ),
    )
    connection.execute(
        "insert into cursorDiskKV(key, value) values (?, ?)",
        (
            "bubbleId:composer-123:assistant-2",
            json.dumps(
                {
                    "bubbleId": "assistant-2",
                    "type": 2,
                    "text": "New followup answer.",
                    "createdAt": "2026-04-13T18:49:22.740Z",
                }
            ),
        ),
    )
    connection.commit()
    connection.close()

    updated = tail.snapshot_updates(include_existing=False)

    assert len(updated) == 1
    assert updated[0].kind == "new"
    assert updated[0].delta_text == "New followup answer."


def test_list_workspace_composers_prefers_recent_unarchived_threads(tmp_path) -> None:
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    _write_workspace_storage(tmp_path, workspace_root, "composer-123")
    _write_global_storage(
        tmp_path,
        workspace_root=workspace_root,
        composer_id="composer-123",
        user_text="What is RepoLine?",
        assistant_text="RepoLine is a voice bridge.",
        name="Latest active thread",
        last_updated_at=200,
    )

    global_db = (
        tmp_path
        / "Library"
        / "Application Support"
        / "Cursor"
        / "User"
        / "globalStorage"
        / "state.vscdb"
    )
    connection = sqlite3.connect(global_db)
    connection.execute(
        "update ItemTable set value = ? where key = ?",
        (
            json.dumps(
                {
                    "allComposers": [
                        {
                            "composerId": "composer-archived",
                            "name": "Older archived thread",
                            "isArchived": True,
                            "lastUpdatedAt": 300,
                            "workspaceIdentifier": {
                                "uri": {"fsPath": str(workspace_root.resolve())}
                            },
                        },
                        {
                            "composerId": "composer-123",
                            "name": "Latest active thread",
                            "isArchived": False,
                            "lastUpdatedAt": 200,
                            "workspaceIdentifier": {
                                "uri": {"fsPath": str(workspace_root.resolve())}
                            },
                        },
                    ]
                }
            ),
            "composer.composerHeaders",
        ),
    )
    connection.commit()
    connection.close()

    summaries = list_workspace_composers(
        workspace_root,
        cursor_support_dir=tmp_path / "Library" / "Application Support" / "Cursor",
    )

    assert [summary.composer_id for summary in summaries] == ["composer-123"]
    assert summaries[0].name == "Latest active thread"


def test_search_workspace_conversations_finds_matching_bubbles(tmp_path) -> None:
    workspace_root = tmp_path / "repo"
    workspace_root.mkdir()
    _write_workspace_storage(tmp_path, workspace_root, "composer-123")
    _write_global_storage(
        tmp_path,
        workspace_root=workspace_root,
        composer_id="composer-123",
        user_text="Tell me about alpha context",
        assistant_text="Alpha context explains RepoLine.",
        name="Alpha thread",
        last_updated_at=200,
    )

    hits = search_workspace_conversations(
        workspace_root,
        "alpha context",
        cursor_support_dir=tmp_path / "Library" / "Application Support" / "Cursor",
    )

    assert len(hits) == 1
    assert hits[0].composer.composer_id == "composer-123"
    assert [bubble.role for bubble in hits[0].matching_bubbles] == ["user", "assistant"]
