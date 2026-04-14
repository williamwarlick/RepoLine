const crypto = require("node:crypto");
const fs = require("node:fs");
const net = require("node:net");
const os = require("node:os");
const path = require("node:path");
const vscode = require("vscode");

const EXTENSION_ID = "repoline.cursor-app-bridge";
const SOCKET_PREFIX = "rlca";
const MAX_LISTED_COMMANDS = 512;
const FOLLOWUP_FOCUS_DELAY_MS = 35;
const FOLLOWUP_OPEN_DELAY_MS = 45;
const PASTE_DELAY_MS = 25;
const SEND_DELAY_MS = 90;
const OPEN_SEND_DELAY_MS = 140;

let outputChannel;

function activate(context) {
  outputChannel = vscode.window.createOutputChannel("RepoLine Cursor App Bridge");
  context.subscriptions.push(outputChannel);

  const workspacePath = getWorkspacePath();
  if (!workspacePath) {
    outputChannel.appendLine("No workspace folder is open; bridge not started.");
    return;
  }

  const state = computeBridgeState(workspacePath);
  ensureDirectoryRemoved(state.socketPath);

  const server = net.createServer((socket) => {
    socket.setEncoding("utf8");
    let buffer = "";

    socket.on("data", (chunk) => {
      buffer += chunk;
      while (true) {
        const newlineIndex = buffer.indexOf("\n");
        if (newlineIndex < 0) {
          break;
        }
        const line = buffer.slice(0, newlineIndex).trim();
        buffer = buffer.slice(newlineIndex + 1);
        if (!line) {
          continue;
        }
        handleSocketRequest(socket, line, workspacePath).catch((error) => {
          writeSocketResponse(socket, {
            ok: false,
            error: toErrorPayload(error),
          });
        });
      }
    });

    socket.on("error", (error) => {
      outputChannel.appendLine(`Socket error: ${String(error)}`);
    });
  });

  server.listen(state.socketPath, () => {
    try {
      fs.writeFileSync(
        state.statePath,
        JSON.stringify(
          {
            extensionId: EXTENSION_ID,
            workspacePath,
            socketPath: state.socketPath,
            statePath: state.statePath,
            activatedAt: new Date().toISOString(),
            pid: process.pid,
          },
          null,
          2
        )
      );
      outputChannel.appendLine(`Bridge listening on ${state.socketPath}`);
    } catch (error) {
      outputChannel.appendLine(`Failed to write bridge state: ${String(error)}`);
    }
  });

  server.on("error", (error) => {
    outputChannel.appendLine(`Bridge server error: ${String(error)}`);
  });

  context.subscriptions.push({
    dispose() {
      try {
        server.close();
      } catch {}
      ensureDirectoryRemoved(state.socketPath);
      ensureFileRemoved(state.statePath);
    },
  });

  context.subscriptions.push(
    vscode.commands.registerCommand(
      "repoline.cursorAppBridge.showStatus",
      async () => {
        const status = await buildBridgeStatus(workspacePath);
        const document = await vscode.workspace.openTextDocument({
          content: JSON.stringify(status, null, 2),
          language: "json",
        });
        await vscode.window.showTextDocument(document, { preview: false });
      }
    )
  );
}

function deactivate() {}

async function handleSocketRequest(socket, line, workspacePath) {
  const request = JSON.parse(line);
  const method = String(request.method || "").trim();

  let result;
  switch (method) {
    case "ping":
      result = await buildBridgeStatus(workspacePath);
      break;
    case "exec":
      result = await executeBridgeCommand(request);
      break;
    case "submitOpenAndSend":
      result = await submitViaOpenAndSend({
        workspacePath,
        prompt: String(request.prompt || ""),
      });
      break;
    case "submitFollowupAndSend":
      result = await submitViaFollowupAndSend({
        workspacePath,
        prompt: String(request.prompt || ""),
      });
      break;
    case "submit":
      result = await submitPrompt({
        workspacePath,
        prompt: String(request.prompt || ""),
        composerId:
          typeof request.composerId === "string" && request.composerId.trim()
            ? request.composerId.trim()
            : undefined,
      });
      break;
    case "submitFollowupClipboardAndSend":
      result = await submitViaFollowupClipboardAndSend({
        workspacePath,
        prompt: String(request.prompt || ""),
      });
      break;
    case "submitStartPromptClipboardAndSend":
      result = await submitViaStartPromptClipboardAndSend({
        workspacePath,
        prompt: String(request.prompt || ""),
      });
      break;
    case "submitOpenDetachedAndSend":
      result = await submitViaOpenDetachedAndSend({
        workspacePath,
        prompt: String(request.prompt || ""),
      });
      break;
    case "submitTestOpenDetachedAndSend":
      result = await submitViaTestOpenDetachedAndSend({
        workspacePath,
        prompt: String(request.prompt || ""),
      });
      break;
    default:
      throw new Error(`Unsupported bridge method: ${method}`);
  }

  writeSocketResponse(socket, {
    ok: true,
    result,
  });
}

async function buildBridgeStatus(workspacePath) {
  const allCommands = await vscode.commands.getCommands(true);
  const composerCommands = allCommands
    .filter((command) => /(composer|chat)/i.test(command))
    .sort();
  const selectedComposerIds = await safeExecuteCommand(
    "composer.getOrderedSelectedComposerIds"
  );
  const selectedComposerId = Array.isArray(selectedComposerIds)
    ? selectedComposerIds[0]
    : undefined;
  const handleProbe = selectedComposerId
    ? await probeComposerHandle(selectedComposerId)
    : {
        ok: false,
        error: "No selected composer ID",
      };

  return {
    extensionId: EXTENSION_ID,
    workspacePath,
    selectedComposerIds: Array.isArray(selectedComposerIds)
      ? selectedComposerIds
      : [],
    selectedComposerId,
    handleProbe,
    composerCommandCount: composerCommands.length,
    composerCommands: composerCommands.slice(0, MAX_LISTED_COMMANDS),
  };
}

async function submitPrompt({ workspacePath, prompt, composerId }) {
  if (!prompt.trim()) {
    throw new Error("Prompt is required.");
  }

  const errors = [];
  const strategies = [
    async () => {
      if (!composerId) {
        throw new Error("Cursor bridge could not determine a selected composer ID.");
      }
      return await submitViaComposerHandle({
        workspacePath,
        prompt,
        composerId,
      });
    },
    async () => submitViaOpenDetachedAndSend({ workspacePath, prompt }),
    async () => submitViaFollowupClipboardAndSend({ workspacePath, prompt }),
    async () => submitViaStartPromptClipboardAndSend({ workspacePath, prompt }),
    async () => submitViaTestOpenDetachedAndSend({ workspacePath, prompt }),
    async () => submitViaOpenAndSend({ workspacePath, prompt }),
    async () => submitViaFollowupAndSend({ workspacePath, prompt }),
  ];

  for (const strategy of strategies) {
    try {
      return await strategy();
    } catch (error) {
      errors.push(String(error instanceof Error ? error.message : error));
    }
  }

  throw new Error(
    `Cursor bridge could not submit the prompt. ${errors.join(" | ")}`
  );
}

async function submitViaComposerHandle({ workspacePath, prompt, composerId }) {
  const handle = await vscode.commands.executeCommand(
    "composer.getComposerHandleById",
    composerId
  );

  if (!handle || typeof handle.submitMessage !== "function") {
    throw new Error(
      "Cursor bridge resolved a composer handle, but submitMessage is not callable."
    );
  }

  const startedAt = Date.now();
  await handle.submitMessage(undefined, undefined, prompt);

  return {
    workspacePath,
    composerId,
    via: "composer.getComposerHandleById.submitMessage",
    submittedAt: new Date().toISOString(),
    durationMs: Date.now() - startedAt,
  };
}

async function submitViaFollowupClipboardAndSend({ workspacePath, prompt }) {
  if (!prompt.trim()) {
    throw new Error("Prompt is required.");
  }

  const before = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  await vscode.commands.executeCommand("composer.focusComposer");
  await sleep(FOLLOWUP_FOCUS_DELAY_MS);
  await vscode.commands.executeCommand("aichat.newfollowupaction");
  await sleep(FOLLOWUP_OPEN_DELAY_MS);
  await vscode.env.clipboard.writeText(prompt);
  await vscode.commands.executeCommand("editor.action.clipboardPasteAction");
  await sleep(PASTE_DELAY_MS);
  await vscode.commands.executeCommand("composer.sendToAgent");
  await sleep(SEND_DELAY_MS);
  const after = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  const composerId = resolveComposerIdFromSelectionChange(before, after);

  return {
    workspacePath,
    beforeSelectedComposerIds: Array.isArray(before) ? before : [],
    afterSelectedComposerIds: Array.isArray(after) ? after : [],
    composerId,
    via: "composer.focusComposer+aichat.newfollowupaction+editor.action.clipboardPasteAction+composer.sendToAgent",
  };
}

async function submitViaStartPromptClipboardAndSend({ workspacePath, prompt }) {
  if (!prompt.trim()) {
    throw new Error("Prompt is required.");
  }

  const before = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  await vscode.commands.executeCommand("composer.startComposerPrompt2");
  await sleep(FOLLOWUP_OPEN_DELAY_MS);
  await vscode.env.clipboard.writeText(prompt);
  await vscode.commands.executeCommand("editor.action.clipboardPasteAction");
  await sleep(PASTE_DELAY_MS);
  await vscode.commands.executeCommand("composer.sendToAgent");
  await sleep(SEND_DELAY_MS);
  const after = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  const composerId = resolveComposerIdFromSelectionChange(before, after);

  return {
    workspacePath,
    beforeSelectedComposerIds: Array.isArray(before) ? before : [],
    afterSelectedComposerIds: Array.isArray(after) ? after : [],
    composerId,
    via: "composer.startComposerPrompt2+editor.action.clipboardPasteAction+composer.sendToAgent",
  };
}

async function submitViaOpenAndSend({ workspacePath, prompt }) {
  if (!prompt.trim()) {
    throw new Error("Prompt is required.");
  }

  const before = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  await vscode.commands.executeCommand("workbench.action.chat.open", {
    query: prompt,
  });
  await sleep(60);
  await vscode.commands.executeCommand("composer.sendToAgent");
  await sleep(60);
  const after = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  const composerId = resolveComposerIdFromSelectionChange(before, after);

  return {
    workspacePath,
    beforeSelectedComposerIds: Array.isArray(before) ? before : [],
    afterSelectedComposerIds: Array.isArray(after) ? after : [],
    composerId,
    via: "workbench.action.chat.open+composer.sendToAgent",
  };
}

async function submitViaOpenDetachedAndSend({ workspacePath, prompt }) {
  if (!prompt.trim()) {
    throw new Error("Prompt is required.");
  }

  const before = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  fireAndForgetCommand("workbench.action.chat.open", prompt);
  await sleep(OPEN_SEND_DELAY_MS);
  await vscode.commands.executeCommand("composer.sendToAgent");
  await sleep(SEND_DELAY_MS);
  const after = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  const composerId = resolveComposerIdFromSelectionChange(before, after);

  return {
    workspacePath,
    beforeSelectedComposerIds: Array.isArray(before) ? before : [],
    afterSelectedComposerIds: Array.isArray(after) ? after : [],
    composerId,
    via: "workbench.action.chat.open(detached)+composer.sendToAgent",
  };
}

async function submitViaTestOpenDetachedAndSend({ workspacePath, prompt }) {
  if (!prompt.trim()) {
    throw new Error("Prompt is required.");
  }

  const before = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  fireAndForgetCommand("workbench.action.chat.testOpenWithPrompt", prompt);
  await sleep(OPEN_SEND_DELAY_MS);
  await vscode.commands.executeCommand("composer.sendToAgent");
  await sleep(SEND_DELAY_MS);
  const after = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  const composerId = resolveComposerIdFromSelectionChange(before, after);

  return {
    workspacePath,
    beforeSelectedComposerIds: Array.isArray(before) ? before : [],
    afterSelectedComposerIds: Array.isArray(after) ? after : [],
    composerId,
    via: "workbench.action.chat.testOpenWithPrompt(detached)+composer.sendToAgent",
  };
}

async function submitViaFollowupAndSend({ workspacePath, prompt }) {
  if (!prompt.trim()) {
    throw new Error("Prompt is required.");
  }

  const before = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  await vscode.commands.executeCommand("composer.focusComposer");
  await sleep(30);
  await vscode.commands.executeCommand("aichat.newfollowupaction");
  await sleep(30);
  await vscode.commands.executeCommand("type", { text: prompt });
  await sleep(30);
  await vscode.commands.executeCommand("composer.sendToAgent");
  await sleep(60);
  const after = await safeExecuteCommand("composer.getOrderedSelectedComposerIds");
  const composerId = resolveComposerIdFromSelectionChange(before, after);

  return {
    workspacePath,
    beforeSelectedComposerIds: Array.isArray(before) ? before : [],
    afterSelectedComposerIds: Array.isArray(after) ? after : [],
    composerId,
    via: "composer.focusComposer+aichat.newfollowupaction+type+composer.sendToAgent",
  };
}

function fireAndForgetCommand(command, ...args) {
  void vscode.commands.executeCommand(command, ...args).catch((error) => {
    outputChannel.appendLine(
      `[fire-and-forget] ${command} failed: ${String(
        error instanceof Error ? error.message : error
      )}`
    );
  });
}

function resolveComposerIdFromSelectionChange(before, after) {
  const beforeIds = Array.isArray(before) ? before : [];
  const afterIds = Array.isArray(after) ? after : [];
  for (const composerId of afterIds) {
    if (!beforeIds.includes(composerId)) {
      return composerId;
    }
  }
  return afterIds[0];
}

async function probeComposerHandle(composerId) {
  try {
    const handle = await vscode.commands.executeCommand(
      "composer.getComposerHandleById",
      composerId
    );
    const ownKeys =
      handle && typeof handle === "object"
        ? Reflect.ownKeys(handle).map((key) => String(key))
        : [];
    return {
      ok: true,
      type: typeof handle,
      ownKeys,
      hasSubmitMessage:
        !!handle && typeof handle.submitMessage === "function",
    };
  } catch (error) {
    return {
      ok: false,
      error: toErrorPayload(error),
    };
  }
}

async function safeExecuteCommand(command, ...args) {
  try {
    return await vscode.commands.executeCommand(command, ...args);
  } catch (error) {
    return {
      error: toErrorPayload(error),
    };
  }
}

async function executeBridgeCommand(request) {
  const command = String(request.command || "").trim();
  if (!command) {
    throw new Error("Command name is required.");
  }

  const args = Array.isArray(request.args) ? request.args : [];
  const startedAt = Date.now();
  const result = await safeExecuteCommand(command, ...args);
  return {
    command,
    args,
    durationMs: Date.now() - startedAt,
    result: sanitizeForJson(result),
  };
}

function computeBridgeState(workspacePath) {
  const hash = crypto.createHash("sha1").update(workspacePath).digest("hex");
  return {
    socketPath: path.join("/tmp", `${SOCKET_PREFIX}-${hash}.sock`),
    statePath: path.join("/tmp", `${SOCKET_PREFIX}-${hash}.json`),
  };
}

function getWorkspacePath() {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return folder?.uri?.scheme === "file" ? folder.uri.fsPath : undefined;
}

function writeSocketResponse(socket, payload) {
  socket.write(`${JSON.stringify(payload)}\n`);
  socket.end();
}

function toErrorPayload(error) {
  if (error instanceof Error) {
    return {
      message: error.message,
      stack: error.stack,
    };
  }
  return {
    message: String(error),
  };
}

function sanitizeForJson(value) {
  if (value === null || value === undefined) {
    return value ?? null;
  }
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  if (Array.isArray(value)) {
    return value.map((item) => sanitizeForJson(item));
  }
  if (typeof value === "object") {
    const entries = [];
    for (const key of Reflect.ownKeys(value)) {
      const stringKey = String(key);
      const entryValue = value[key];
      if (typeof entryValue === "function") {
        continue;
      }
      entries.push([stringKey, sanitizeForJson(entryValue)]);
    }
    return Object.fromEntries(entries);
  }
  return String(value);
}

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function ensureDirectoryRemoved(filePath) {
  try {
    fs.unlinkSync(filePath);
  } catch {}
}

function ensureFileRemoved(filePath) {
  try {
    fs.unlinkSync(filePath);
  } catch {}
}

module.exports = {
  activate,
  deactivate,
};
