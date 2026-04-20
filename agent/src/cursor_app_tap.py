from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse


class CursorAppTapError(RuntimeError):
    """Raised when the local Cursor app state cannot be read safely."""


@dataclass(frozen=True)
class CursorBubble:
    composer_id: str
    bubble_id: str
    bubble_type: int
    text: str
    created_at: str | None
    request_id: str | None
    capability_type: int | None
    raw: dict[str, Any]

    @property
    def role(self) -> str:
        return "user" if self.bubble_type == 1 else "assistant"

    @property
    def is_tool_event(self) -> bool:
        return self.capability_type is not None or "toolFormerData" in self.raw


@dataclass(frozen=True)
class CursorBubbleUpdate:
    kind: str
    bubble: CursorBubble
    previous_text: str
    delta_text: str


@dataclass(frozen=True)
class CursorComposerSummary:
    composer_id: str
    name: str | None
    is_archived: bool
    last_updated_at: int | None


@dataclass(frozen=True)
class CursorConversationSearchHit:
    composer: CursorComposerSummary
    matching_bubbles: list[CursorBubble]


def compute_delta_text(previous_text: str, current_text: str) -> str:
    prefix_length = 0
    limit = min(len(previous_text), len(current_text))
    while (
        prefix_length < limit
        and previous_text[prefix_length] == current_text[prefix_length]
    ):
        prefix_length += 1
    return current_text[prefix_length:]


def default_cursor_support_dir() -> Path:
    return Path("~/Library/Application Support/Cursor").expanduser()


def default_global_state_db(cursor_support_dir: Path | None = None) -> Path:
    support_dir = cursor_support_dir or default_cursor_support_dir()
    return support_dir / "User" / "globalStorage" / "state.vscdb"


def decode_sqlite_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "ignore")
    if isinstance(value, str):
        return value
    raise CursorAppTapError(f"Unsupported SQLite value type: {type(value)!r}")


def parse_workspace_folder_uri(uri: str) -> Path | None:
    if not uri.startswith("file://"):
        return None
    parsed = urlparse(uri)
    return Path(unquote(parsed.path)).resolve()


def find_workspace_storage_dir(
    workspace_root: str | Path,
    *,
    cursor_support_dir: Path | None = None,
) -> Path:
    support_dir = cursor_support_dir or default_cursor_support_dir()
    storage_root = support_dir / "User" / "workspaceStorage"
    workspace_path = Path(workspace_root).expanduser().resolve()
    candidates: list[tuple[float, Path]] = []

    for workspace_json in storage_root.glob("*/workspace.json"):
        try:
            payload = json.loads(workspace_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        folder_path = parse_workspace_folder_uri(payload.get("folder", ""))
        if folder_path == workspace_path:
            candidates.append((workspace_json.stat().st_mtime, workspace_json.parent))

    if not candidates:
        raise CursorAppTapError(
            f"Could not find Cursor workspace storage for {workspace_path}."
        )

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def read_item_table_json(db_path: Path, key: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "select value from ItemTable where key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return None

    return json.loads(decode_sqlite_value(row[0]))


def write_item_table_json(db_path: Path, key: str, payload: dict[str, Any]) -> None:
    encoded_payload = json.dumps(payload)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "update ItemTable set value = ? where key = ?",
            (encoded_payload, key),
        )
        connection.commit()


def find_active_composer_id(
    workspace_root: str | Path,
    *,
    cursor_support_dir: Path | None = None,
) -> str:
    workspace_storage_dir = find_workspace_storage_dir(
        workspace_root, cursor_support_dir=cursor_support_dir
    )
    workspace_db = workspace_storage_dir / "state.vscdb"
    composer_state = read_item_table_json(workspace_db, "composer.composerData")

    if composer_state:
        selected_ids = composer_state.get("selectedComposerIds") or []
        if selected_ids:
            return selected_ids[0]
        focused_ids = composer_state.get("lastFocusedComposerIds") or []
        if focused_ids:
            return focused_ids[0]

    support_dir = cursor_support_dir or default_cursor_support_dir()
    global_db = default_global_state_db(support_dir)
    headers_state = read_item_table_json(global_db, "composer.composerHeaders")
    workspace_path = str(Path(workspace_root).expanduser().resolve())
    if headers_state:
        matching_heads = []
        for composer in headers_state.get("allComposers", []):
            workspace_uri = (
                composer.get("workspaceIdentifier", {})
                .get("uri", {})
                .get("fsPath")
            )
            if workspace_uri != workspace_path:
                continue
            if composer.get("isArchived"):
                continue
            matching_heads.append(composer)
        if matching_heads:
            matching_heads.sort(
                key=lambda composer: composer.get("lastUpdatedAt", 0), reverse=True
            )
            composer_id = matching_heads[0].get("composerId")
            if composer_id:
                return composer_id

    raise CursorAppTapError(
        f"Could not determine an active composer for {workspace_path}."
    )


def list_selected_composer_ids(
    workspace_root: str | Path,
    *,
    cursor_support_dir: Path | None = None,
) -> list[str]:
    workspace_storage_dir = find_workspace_storage_dir(
        workspace_root, cursor_support_dir=cursor_support_dir
    )
    workspace_db = workspace_storage_dir / "state.vscdb"
    composer_state = read_item_table_json(workspace_db, "composer.composerData") or {}

    selected_ids: list[str] = []
    for value in composer_state.get("selectedComposerIds") or []:
        if not isinstance(value, str):
            continue
        normalized_id = value.strip()
        if normalized_id and normalized_id not in selected_ids:
            selected_ids.append(normalized_id)

    for value in composer_state.get("lastFocusedComposerIds") or []:
        if not isinstance(value, str):
            continue
        normalized_id = value.strip()
        if normalized_id and normalized_id not in selected_ids:
            selected_ids.append(normalized_id)

    return selected_ids


def list_workspace_composers(
    workspace_root: str | Path,
    *,
    cursor_support_dir: Path | None = None,
    include_archived: bool = False,
) -> list[CursorComposerSummary]:
    support_dir = cursor_support_dir or default_cursor_support_dir()
    global_db = default_global_state_db(support_dir)
    headers_state = read_item_table_json(global_db, "composer.composerHeaders") or {}
    workspace_path = str(Path(workspace_root).expanduser().resolve())

    summaries: list[CursorComposerSummary] = []
    for composer in headers_state.get("allComposers", []):
        workspace_uri = (
            composer.get("workspaceIdentifier", {})
            .get("uri", {})
            .get("fsPath")
        )
        if workspace_uri != workspace_path:
            continue
        is_archived = bool(composer.get("isArchived"))
        if is_archived and not include_archived:
            continue
        composer_id = composer.get("composerId")
        if not composer_id:
            continue
        last_updated_at = composer.get("lastUpdatedAt")
        summaries.append(
            CursorComposerSummary(
                composer_id=composer_id,
                name=composer.get("name"),
                is_archived=is_archived,
                last_updated_at=int(last_updated_at)
                if isinstance(last_updated_at, (int, float))
                else None,
            )
        )

    summaries.sort(
        key=lambda composer: composer.last_updated_at or 0,
        reverse=True,
    )
    return summaries


def search_workspace_conversations(
    workspace_root: str | Path,
    query: str,
    *,
    cursor_support_dir: Path | None = None,
    include_archived: bool = True,
    limit: int = 10,
    per_conversation_limit: int = 3,
) -> list[CursorConversationSearchHit]:
    normalized_query = query.strip().lower()
    if not normalized_query:
        return []

    results: list[CursorConversationSearchHit] = []
    for composer in list_workspace_composers(
        workspace_root,
        cursor_support_dir=cursor_support_dir,
        include_archived=include_archived,
    ):
        try:
            bubbles = load_bubbles(
                composer.composer_id, cursor_support_dir=cursor_support_dir
            )
        except CursorAppTapError:
            continue
        matches = [
            bubble
            for bubble in bubbles
            if normalized_query in (bubble.text or "").lower()
        ]
        if not matches:
            continue
        results.append(
            CursorConversationSearchHit(
                composer=composer,
                matching_bubbles=matches[:per_conversation_limit],
            )
        )
        if len(results) >= limit:
            break

    return results


def read_cursor_disk_kv_json(db_path: Path, key: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "select value from cursorDiskKV where key = ?",
            (key,),
        ).fetchone()

    if row is None:
        return None

    return json.loads(decode_sqlite_value(row[0]))


def write_cursor_disk_kv_json(db_path: Path, key: str, payload: dict[str, Any]) -> None:
    encoded_payload = json.dumps(payload)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "update cursorDiskKV set value = ? where key = ?",
            (encoded_payload, key),
        )
        connection.commit()


def load_composer_data(
    composer_id: str,
    *,
    cursor_support_dir: Path | None = None,
) -> dict[str, Any]:
    global_db = default_global_state_db(cursor_support_dir)
    data = read_cursor_disk_kv_json(global_db, f"composerData:{composer_id}")
    if data is None:
        raise CursorAppTapError(f"Could not load composerData for {composer_id}.")
    return data


def write_composer_data(
    composer_id: str,
    payload: dict[str, Any],
    *,
    cursor_support_dir: Path | None = None,
) -> None:
    global_db = default_global_state_db(cursor_support_dir)
    write_cursor_disk_kv_json(global_db, f"composerData:{composer_id}", payload)


def build_cursor_model_config(
    model: str,
    *,
    existing_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    base_config = dict(existing_config or {})
    if model == "composer-2-fast":
        return {
            **base_config,
            "modelName": "composer-2",
            "maxMode": False,
            "selectedModels": [
                {
                    "modelId": "composer-2",
                    "parameters": [{"id": "fast", "value": "true"}],
                }
            ],
        }
    if model == "composer-2":
        return {
            **base_config,
            "modelName": "composer-2",
            "maxMode": False,
            "selectedModels": [
                {
                    "modelId": "composer-2",
                    "parameters": [{"id": "fast", "value": "false"}],
                }
            ],
        }
    raise CursorAppTapError(f"Unsupported Cursor app runtime model: {model}")


def _composer_has_history(
    composer_id: str | None,
    *,
    cursor_support_dir: Path | None = None,
) -> bool:
    if not composer_id:
        return False
    try:
        return bool(load_bubbles(composer_id, cursor_support_dir=cursor_support_dir))
    except CursorAppTapError:
        return False


def resolve_runtime_composer_ids(
    workspace_root: str | Path,
    *,
    cursor_support_dir: Path | None = None,
) -> list[str]:
    candidate_ids = list_selected_composer_ids(
        workspace_root, cursor_support_dir=cursor_support_dir
    )
    active_composer_id: str | None = None
    try:
        active_composer_id = find_active_composer_id(
            workspace_root, cursor_support_dir=cursor_support_dir
        )
    except CursorAppTapError:
        active_composer_id = None

    if active_composer_id and active_composer_id not in candidate_ids:
        candidate_ids.append(active_composer_id)

    preferred_ids = [
        composer_id
        for composer_id in candidate_ids
        if _composer_has_history(composer_id, cursor_support_dir=cursor_support_dir)
    ]
    if preferred_ids:
        return preferred_ids
    if candidate_ids:
        return candidate_ids
    if active_composer_id:
        return [active_composer_id]
    return []


def resolve_runtime_composer_id(
    workspace_root: str | Path,
    *,
    cursor_support_dir: Path | None = None,
) -> str | None:
    candidate_ids = resolve_runtime_composer_ids(
        workspace_root, cursor_support_dir=cursor_support_dir
    )
    return candidate_ids[0] if candidate_ids else None


def update_cursor_runtime_model(
    workspace_root: str | Path,
    *,
    model: str,
    cursor_support_dir: Path | None = None,
) -> list[str]:
    runtime_composer_ids = resolve_runtime_composer_ids(
        workspace_root, cursor_support_dir=cursor_support_dir
    )
    if not runtime_composer_ids:
        raise CursorAppTapError("Could not determine a Cursor app composer to update.")

    updated_composer_ids: list[str] = []
    for composer_id in runtime_composer_ids:
        composer_data = load_composer_data(
            composer_id, cursor_support_dir=cursor_support_dir
        )
        composer_data["modelConfig"] = build_cursor_model_config(
            model,
            existing_config=composer_data.get("modelConfig"),
        )
        write_composer_data(
            composer_id,
            composer_data,
            cursor_support_dir=cursor_support_dir,
        )
        updated_composer_ids.append(composer_id)

    global_db = default_global_state_db(cursor_support_dir)
    app_state_key = (
        "src.vs.platform.reactivestorage.browser.reactiveStorageServiceImpl."
        "persistentStorage.applicationUser"
    )
    app_state = read_item_table_json(global_db, app_state_key)
    if app_state is not None:
        ai_settings = app_state.setdefault("aiSettings", {})
        model_config = ai_settings.setdefault("modelConfig", {})
        model_config["composer"] = build_cursor_model_config(
            model,
            existing_config=model_config.get("composer"),
        )
        write_item_table_json(global_db, app_state_key, app_state)

    return updated_composer_ids


def load_bubble_data(
    composer_id: str,
    bubble_id: str,
    *,
    cursor_support_dir: Path | None = None,
) -> dict[str, Any]:
    global_db = default_global_state_db(cursor_support_dir)
    data = read_cursor_disk_kv_json(global_db, f"bubbleId:{composer_id}:{bubble_id}")
    if data is None:
        raise CursorAppTapError(
            f"Could not load bubbleId:{composer_id}:{bubble_id} from Cursor state."
        )
    return data


def load_bubbles(
    composer_id: str,
    *,
    cursor_support_dir: Path | None = None,
) -> list[CursorBubble]:
    composer_data = load_composer_data(
        composer_id, cursor_support_dir=cursor_support_dir
    )
    bubbles: list[CursorBubble] = []
    for header in composer_data.get("fullConversationHeadersOnly", []):
        bubble_id = header.get("bubbleId")
        bubble_type = header.get("type")
        if not bubble_id or bubble_type is None:
            continue
        bubble_data = load_bubble_data(
            composer_id, bubble_id, cursor_support_dir=cursor_support_dir
        )
        bubbles.append(
            CursorBubble(
                composer_id=composer_id,
                bubble_id=bubble_id,
                bubble_type=int(bubble_type),
                text=bubble_data.get("text", ""),
                created_at=bubble_data.get("createdAt"),
                request_id=bubble_data.get("requestId"),
                capability_type=bubble_data.get("capabilityType"),
                raw=bubble_data,
            )
        )
    return bubbles


class CursorComposerTail:
    def __init__(
        self,
        composer_id: str,
        *,
        cursor_support_dir: Path | None = None,
    ) -> None:
        self.composer_id = composer_id
        self.cursor_support_dir = cursor_support_dir
        self._known_text_by_bubble: dict[str, str] = {}
        self._did_initial_snapshot = False

    def seed_known_bubbles(self, bubbles: list[CursorBubble]) -> None:
        for bubble in bubbles:
            self._known_text_by_bubble[bubble.bubble_id] = bubble.text

    def snapshot_updates(self, *, include_existing: bool = False) -> list[CursorBubbleUpdate]:
        updates: list[CursorBubbleUpdate] = []
        for bubble in load_bubbles(
            self.composer_id, cursor_support_dir=self.cursor_support_dir
        ):
            previous_text = self._known_text_by_bubble.get(bubble.bubble_id)
            if previous_text is None:
                self._known_text_by_bubble[bubble.bubble_id] = bubble.text
                if include_existing or self._did_initial_snapshot:
                    updates.append(
                        CursorBubbleUpdate(
                            kind="new",
                            bubble=bubble,
                            previous_text="",
                            delta_text=bubble.text,
                        )
                    )
                continue

            if bubble.text == previous_text:
                continue

            delta_text = compute_delta_text(previous_text, bubble.text)
            self._known_text_by_bubble[bubble.bubble_id] = bubble.text
            updates.append(
                CursorBubbleUpdate(
                    kind="update",
                    bubble=bubble,
                    previous_text=previous_text,
                    delta_text=delta_text,
                )
            )

        self._did_initial_snapshot = True
        return updates


def update_to_json(update: CursorBubbleUpdate) -> str:
    return json.dumps(
        {
            "kind": update.kind,
            "composer_id": update.bubble.composer_id,
            "bubble_id": update.bubble.bubble_id,
            "bubble_type": update.bubble.bubble_type,
            "role": update.bubble.role,
            "created_at": update.bubble.created_at,
            "request_id": update.bubble.request_id,
            "capability_type": update.bubble.capability_type,
            "is_tool_event": update.bubble.is_tool_event,
            "text": update.bubble.text,
            "delta_text": update.delta_text,
        },
        ensure_ascii=True,
    )


def follow_composer(
    composer_id: str,
    *,
    cursor_support_dir: Path | None = None,
    include_existing: bool = True,
    poll_interval_seconds: float = 0.1,
):
    tail = CursorComposerTail(composer_id, cursor_support_dir=cursor_support_dir)
    for update in tail.snapshot_updates(include_existing=include_existing):
        yield update
    while True:
        time.sleep(poll_interval_seconds)
        for update in tail.snapshot_updates(include_existing=False):
            yield update
