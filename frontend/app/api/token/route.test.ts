import { afterEach, expect, test } from 'bun:test';
import { decodeJwt } from 'jose';
import { POST } from './route';

const ORIGINAL_ENV = { ...process.env };

afterEach(() => {
  for (const key of Object.keys(process.env)) {
    if (!(key in ORIGINAL_ENV)) {
      delete process.env[key];
    }
  }

  for (const [key, value] of Object.entries(ORIGINAL_ENV)) {
    if (value === undefined) {
      delete process.env[key];
      continue;
    }
    process.env[key] = value;
  }
});

test('POST returns connection details in production mode', async () => {
  process.env.NODE_ENV = 'production';
  process.env.LIVEKIT_API_KEY = 'test_key';
  process.env.LIVEKIT_API_SECRET = 'test_secret';
  process.env.LIVEKIT_URL = 'wss://example.livekit.cloud';

  const response = await POST(
    new Request('http://localhost/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  );
  const data = await response.json();

  expect(response.status).toBe(200);
  expect(data).toMatchObject({
    serverUrl: 'wss://example.livekit.cloud',
    participantName: 'user',
  });
  expect(response.headers.get('Cache-Control')).toBe('no-store');
  expect(response.headers.get('X-Robots-Tag')).toBe('noindex, nofollow');
});

test('POST reports missing environment variables with controlled errors', async () => {
  process.env.NODE_ENV = 'production';
  delete process.env.LIVEKIT_URL;
  process.env.LIVEKIT_API_KEY = 'test_key';
  process.env.LIVEKIT_API_SECRET = 'test_secret';

  const response = await POST(
    new Request('http://localhost/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  );

  expect(response.status).toBe(500);
  await expect(response.json()).resolves.toEqual({
    error: 'LIVEKIT_URL is not defined',
  });
});

test('POST preserves requested room_config in the participant token', async () => {
  process.env.NODE_ENV = 'production';
  process.env.LIVEKIT_API_KEY = 'test_key';
  process.env.LIVEKIT_API_SECRET = 'test_secret';
  process.env.LIVEKIT_URL = 'wss://example.livekit.cloud';

  const response = await POST(
    new Request('http://localhost/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        room_config: {
          agents: [{ agent_name: 'clawdbot-agent' }],
        },
      }),
    })
  );
  const data = await response.json();
  const claims = decodeJwt(data.participantToken);

  expect(response.status).toBe(200);
  expect(claims.video).toMatchObject({
    room: data.roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  });
  expect(claims.roomConfig).toEqual({
    agents: [{ agent_name: 'clawdbot-agent' }],
  });
});

test('POST trims whitespace around LiveKit environment variables', async () => {
  process.env.NODE_ENV = 'production';
  process.env.LIVEKIT_API_KEY = 'test_key\n';
  process.env.LIVEKIT_API_SECRET = 'test_secret\n';
  process.env.LIVEKIT_URL = 'wss://example.livekit.cloud\n';

  const response = await POST(
    new Request('http://localhost/api/token', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    })
  );
  const data = await response.json();
  const claims = decodeJwt(data.participantToken);

  expect(response.status).toBe(200);
  expect(data.serverUrl).toBe('wss://example.livekit.cloud');
  expect(claims.iss).toBe('test_key');
});
