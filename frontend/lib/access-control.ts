export const ACCESS_COOKIE_NAME = '__Host-repoline_access';
export const ACCESS_PIN_ENV_NAME = 'REPOLINE_ACCESS_PIN';
export const ACCESS_REDIRECT_PARAM = 'next';
export const UNLOCK_PATH = '/unlock';
export const UNLOCK_API_PATH = '/api/unlock';
export const ACCESS_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 2;

const ACCESS_CODE_MIN_LENGTH = 16;
const textEncoder = new TextEncoder();

function encodeBase64Url(bytes: Uint8Array): string {
  const base64 = btoa(Array.from(bytes, (byte) => String.fromCharCode(byte)).join(''));
  return base64.replaceAll('+', '-').replaceAll('/', '_').replaceAll('=', '');
}

function decodeBase64Url(value: string): ArrayBuffer {
  const normalized = value.replaceAll('-', '+').replaceAll('_', '/');
  const padding = normalized.length % 4 === 0 ? '' : '='.repeat(4 - (normalized.length % 4));
  const decoded = atob(`${normalized}${padding}`);
  const bytes = Uint8Array.from(decoded, (char) => char.charCodeAt(0));
  if (encodeBase64Url(bytes) !== value) {
    throw new Error('Invalid base64url encoding');
  }
  return new Uint8Array(bytes).buffer;
}

async function importAccessKey(secret: string, usages: KeyUsage[]): Promise<CryptoKey> {
  return crypto.subtle.importKey(
    'raw',
    textEncoder.encode(secret),
    { name: 'HMAC', hash: 'SHA-256' },
    false,
    usages
  );
}

async function signPayload(payload: string, secret: string): Promise<string> {
  const key = await importAccessKey(secret, ['sign']);
  const signature = await crypto.subtle.sign('HMAC', key, textEncoder.encode(payload));
  return encodeBase64Url(new Uint8Array(signature));
}

async function verifyPayload(payload: string, signature: string, secret: string): Promise<boolean> {
  const key = await importAccessKey(secret, ['verify']);
  return crypto.subtle.verify('HMAC', key, decodeBase64Url(signature), textEncoder.encode(payload));
}

export function isAccessProtectionEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(env[ACCESS_PIN_ENV_NAME]?.trim());
}

export function getConfiguredAccessPin(env: NodeJS.ProcessEnv = process.env): string {
  const pin = env[ACCESS_PIN_ENV_NAME]?.trim();
  if (!pin) {
    throw new Error(`${ACCESS_PIN_ENV_NAME} is not defined`);
  }
  if (pin.length < ACCESS_CODE_MIN_LENGTH) {
    throw new Error(`${ACCESS_PIN_ENV_NAME} must be at least ${ACCESS_CODE_MIN_LENGTH} characters`);
  }
  return pin;
}

export async function createAccessCookieValue(pin: string, now = Date.now()): Promise<string> {
  const exp = Math.floor(now / 1000) + ACCESS_COOKIE_MAX_AGE_SECONDS;
  const payload = encodeBase64Url(textEncoder.encode(JSON.stringify({ exp })));
  const signature = await signPayload(payload, pin);
  return `${payload}.${signature}`;
}

export async function isValidAccessCookie(
  cookieValue: string | undefined,
  env: NodeJS.ProcessEnv = process.env,
  now = Date.now()
): Promise<boolean> {
  if (!isAccessProtectionEnabled(env)) {
    return true;
  }
  if (!cookieValue) {
    return false;
  }

  const [payload, signature] = cookieValue.split('.');
  if (!payload || !signature) {
    return false;
  }

  const configuredPin = getConfiguredAccessPin(env);
  if (!(await verifyPayload(payload, signature, configuredPin))) {
    return false;
  }

  try {
    const decodedPayload = JSON.parse(
      new TextDecoder().decode(new Uint8Array(decodeBase64Url(payload)))
    ) as {
      exp?: number;
    };
    if (typeof decodedPayload.exp !== 'number') {
      return false;
    }

    return decodedPayload.exp > Math.floor(now / 1000);
  } catch {
    return false;
  }
}

export function sanitizeNextPath(nextValue: string | null | undefined): string {
  if (!nextValue || !nextValue.startsWith('/')) {
    return '/';
  }

  if (nextValue.startsWith('//') || nextValue.startsWith('/\\')) {
    return '/';
  }

  return nextValue;
}
