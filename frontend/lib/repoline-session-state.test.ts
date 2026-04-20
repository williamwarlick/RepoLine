import { describe, expect, test } from 'bun:test';
import {
  formatRuntimeModelLabel,
  parseRepolineSessionRuntimeEvent,
} from '@/lib/repoline-session-state';

describe('parseRepolineSessionRuntimeEvent', () => {
  test('parses session state events', () => {
    const event = parseRepolineSessionRuntimeEvent({
      text: JSON.stringify({
        type: 'session_state',
        state: {
          provider: 'cursor',
          providerTransport: 'cli',
          accessPolicy: 'readonly',
          canUpdateModel: true,
          configuredModel: 'composer-2-fast',
          activeModel: 'composer-2-fast',
          modelOptions: ['composer-2-fast', 'composer-2'],
        },
      }),
      streamInfo: {
        id: 'stream-1',
        timestamp: 123,
      },
    } as never);

    expect(event).toEqual({
      id: 'stream-1',
      timestamp: 123,
      requestId: undefined,
      type: 'session_state',
      state: {
        provider: 'cursor',
        providerTransport: 'cli',
        providerSubmitMode: undefined,
        configuredModel: 'composer-2-fast',
        activeModel: 'composer-2-fast',
        thinkingLevel: undefined,
        accessPolicy: 'readonly',
        canUpdateModel: true,
        modelOptions: ['composer-2-fast', 'composer-2'],
        modelUpdateNote: undefined,
      },
    });
  });

  test('parses control results', () => {
    const event = parseRepolineSessionRuntimeEvent({
      text: JSON.stringify({
        type: 'control_result',
        requestId: 'req-1',
        action: 'set_model',
        ok: true,
        message: 'Runtime model updated to composer-2-fast.',
        state: {
          provider: 'cursor',
          providerTransport: 'app',
          accessPolicy: 'readonly',
          canUpdateModel: true,
          activeModel: 'composer-2-fast',
          modelOptions: ['composer-2-fast', 'composer-2'],
          modelUpdateNote: "Cursor App updates the model in Cursor's local runtime state.",
        },
      }),
      streamInfo: {
        id: 'stream-2',
        timestamp: 456,
      },
    } as never);

    expect(event?.type).toBe('control_result');
    if (!event || event.type !== 'control_result') {
      throw new Error('expected a control_result event');
    }

    expect(event.requestId).toBe('req-1');
    expect(event.ok).toBe(true);
    expect(event.state.providerTransport).toBe('app');
    expect(event.state.canUpdateModel).toBe(true);
  });
});

describe('formatRuntimeModelLabel', () => {
  test('humanizes model identifiers', () => {
    expect(formatRuntimeModelLabel('composer-2-fast')).toBe('composer 2 fast');
    expect(formatRuntimeModelLabel(undefined)).toBe('Default model');
  });
});
