import { describe, expect, it } from 'bun:test';

import { resolveVoiceSessionMode } from '@/lib/voice-session';

describe('resolveVoiceSessionMode', () => {
  it('uses sandbox mode when a connection details endpoint is configured', () => {
    expect(
      resolveVoiceSessionMode({
        NEXT_PUBLIC_CONN_DETAILS_ENDPOINT: 'https://sandbox.example.com/details',
      })
    ).toBe('sandbox');
  });

  it('uses endpoint mode when the sandbox endpoint is absent', () => {
    expect(resolveVoiceSessionMode({ NEXT_PUBLIC_CONN_DETAILS_ENDPOINT: undefined })).toBe(
      'endpoint'
    );
  });
});
