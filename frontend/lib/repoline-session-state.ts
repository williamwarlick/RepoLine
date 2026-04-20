import type { TextStreamData } from '@livekit/components-react';

export const REPOLINE_CONTROL_TOPIC = 'repoline.control';
export const REPOLINE_SESSION_STATE_TOPIC = 'repoline.session.state';

export interface RepolineSessionState {
  provider: string;
  providerTransport?: string;
  providerSubmitMode?: string;
  configuredModel?: string;
  activeModel?: string;
  thinkingLevel?: string;
  accessPolicy: string;
  canUpdateModel: boolean;
  modelOptions: string[];
  modelUpdateNote?: string;
}

export interface RepolineSessionStateEvent {
  id: string;
  timestamp: number;
  requestId?: string;
  type: 'session_state';
  state: RepolineSessionState;
}

export interface RepolineControlResultEvent {
  id: string;
  timestamp: number;
  requestId?: string;
  type: 'control_result';
  action: string;
  ok: boolean;
  message: string;
  state: RepolineSessionState;
}

export type RepolineSessionRuntimeEvent = RepolineSessionStateEvent | RepolineControlResultEvent;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function parseState(value: unknown): RepolineSessionState | null {
  if (!isRecord(value)) {
    return null;
  }

  const provider = typeof value.provider === 'string' ? value.provider : null;
  const accessPolicy = typeof value.accessPolicy === 'string' ? value.accessPolicy : null;
  const canUpdateModel = typeof value.canUpdateModel === 'boolean' ? value.canUpdateModel : null;
  const modelOptions = Array.isArray(value.modelOptions)
    ? value.modelOptions.filter((entry): entry is string => typeof entry === 'string')
    : [];

  if (!provider || !accessPolicy || canUpdateModel === null) {
    return null;
  }

  return {
    provider,
    providerTransport:
      typeof value.providerTransport === 'string' ? value.providerTransport : undefined,
    providerSubmitMode:
      typeof value.providerSubmitMode === 'string' ? value.providerSubmitMode : undefined,
    configuredModel: typeof value.configuredModel === 'string' ? value.configuredModel : undefined,
    activeModel: typeof value.activeModel === 'string' ? value.activeModel : undefined,
    thinkingLevel: typeof value.thinkingLevel === 'string' ? value.thinkingLevel : undefined,
    accessPolicy,
    canUpdateModel,
    modelOptions,
    modelUpdateNote: typeof value.modelUpdateNote === 'string' ? value.modelUpdateNote : undefined,
  };
}

export function parseRepolineSessionRuntimeEvent(
  textStream: TextStreamData
): RepolineSessionRuntimeEvent | null {
  const text = textStream.text.trim();
  if (!text) {
    return null;
  }

  let payload: unknown;
  try {
    payload = JSON.parse(text);
  } catch {
    return null;
  }

  if (!isRecord(payload) || typeof payload.type !== 'string') {
    return null;
  }

  const state = parseState(payload.state);
  if (!state) {
    return null;
  }

  const base = {
    id: textStream.streamInfo.id,
    timestamp: textStream.streamInfo.timestamp,
    requestId: typeof payload.requestId === 'string' ? payload.requestId : undefined,
  };

  if (payload.type === 'session_state') {
    return {
      ...base,
      type: 'session_state',
      state,
    };
  }

  if (
    payload.type === 'control_result' &&
    typeof payload.action === 'string' &&
    typeof payload.ok === 'boolean' &&
    typeof payload.message === 'string'
  ) {
    return {
      ...base,
      type: 'control_result',
      action: payload.action,
      ok: payload.ok,
      message: payload.message,
      state,
    };
  }

  return null;
}

export function formatRuntimeModelLabel(model?: string): string {
  if (!model) {
    return 'Default model';
  }
  return model.replaceAll('-', ' ').replaceAll('_', ' ');
}
