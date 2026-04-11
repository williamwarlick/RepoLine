import { AccessToken, type AccessTokenOptions, type VideoGrant } from 'livekit-server-sdk';
import { NextResponse } from 'next/server';

type ConnectionDetails = {
  serverUrl: string;
  roomName: string;
  participantName: string;
  participantToken: string;
};

// don't cache the results
export const revalidate = 0;
export const runtime = 'nodejs';

type RoomConfigPayload = Record<string, unknown>;
type LiveKitCredentials = {
  apiKey: string;
  apiSecret: string;
  livekitUrl: string;
};

function isRoomConfigPayload(value: unknown): value is RoomConfigPayload {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readRequiredEnv(
  env: NodeJS.ProcessEnv,
  key: 'LIVEKIT_URL' | 'LIVEKIT_API_KEY' | 'LIVEKIT_API_SECRET'
): string {
  const value = env[key]?.trim();
  if (!value) {
    throw new Error(`${key} is not defined`);
  }
  return value;
}

function readLiveKitCredentials(env: NodeJS.ProcessEnv = process.env): LiveKitCredentials {
  const livekitUrl = readRequiredEnv(env, 'LIVEKIT_URL');
  const apiKey = readRequiredEnv(env, 'LIVEKIT_API_KEY');
  const apiSecret = readRequiredEnv(env, 'LIVEKIT_API_SECRET');

  return { apiKey, apiSecret, livekitUrl };
}

async function parseRequestBody(req: Request): Promise<unknown> {
  try {
    const text = await req.text();
    if (!text.trim()) {
      return {};
    }

    return JSON.parse(text);
  } catch {
    throw new Error('Request body must be valid JSON');
  }
}

function readRoomConfig(body: unknown): RoomConfigPayload | undefined {
  return isRoomConfigPayload(body) && isRoomConfigPayload(body.room_config)
    ? body.room_config
    : undefined;
}

function buildResponseHeaders(): Headers {
  return new Headers({
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
  });
}

export async function POST(req: Request) {
  try {
    const credentials = readLiveKitCredentials();
    const body = await parseRequestBody(req);
    const roomConfig = readRoomConfig(body);

    const participantName = 'user';
    const participantIdentity = `voice_assistant_user_${Math.floor(Math.random() * 10_000)}`;
    const roomName = `voice_assistant_room_${Math.floor(Math.random() * 10_000)}`;

    const participantToken = await createParticipantToken(
      credentials,
      { identity: participantIdentity, name: participantName },
      roomName,
      roomConfig
    );

    const data: ConnectionDetails = {
      serverUrl: credentials.livekitUrl,
      roomName,
      participantName,
      participantToken,
    };

    return NextResponse.json(data, { headers: buildResponseHeaders() });
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Failed to create LiveKit token';
    console.error(message);
    return NextResponse.json({ error: message }, { status: 500, headers: buildResponseHeaders() });
  }
}

function createParticipantToken(
  credentials: LiveKitCredentials,
  userInfo: AccessTokenOptions,
  roomName: string,
  roomConfig?: RoomConfigPayload
): Promise<string> {
  const at = new AccessToken(credentials.apiKey, credentials.apiSecret, {
    ...userInfo,
    ttl: '15m',
  });
  const grant: VideoGrant = {
    room: roomName,
    roomJoin: true,
    canPublish: true,
    canPublishData: true,
    canSubscribe: true,
  };
  at.addGrant(grant);

  if (roomConfig) {
    // Keep the JWT room config as plain JSON so the client only sees the fields it requested.
    at.roomConfig = roomConfig as unknown as AccessToken['roomConfig'];
  }

  return at.toJwt();
}
