export const ACCESS_COOKIE_NAME = 'repoline_access';
export const ACCESS_PIN_ENV_NAME = 'REPOLINE_ACCESS_PIN';
export const ACCESS_REDIRECT_PARAM = 'next';
export const UNLOCK_PATH = '/unlock';
export const UNLOCK_API_PATH = '/api/unlock';

async function sha256Hex(value: string): Promise<string> {
  const bytes = new TextEncoder().encode(value);
  const digest = await crypto.subtle.digest('SHA-256', bytes);
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, '0')).join('');
}

export function isAccessProtectionEnabled(env: NodeJS.ProcessEnv = process.env): boolean {
  return Boolean(env[ACCESS_PIN_ENV_NAME]?.trim());
}

export function getConfiguredAccessPin(env: NodeJS.ProcessEnv = process.env): string {
  const pin = env[ACCESS_PIN_ENV_NAME]?.trim();
  if (!pin) {
    throw new Error(`${ACCESS_PIN_ENV_NAME} is not defined`);
  }
  return pin;
}

export function createAccessCookieValue(pin: string): Promise<string> {
  return sha256Hex(pin);
}

export async function isValidAccessCookie(
  cookieValue: string | undefined,
  env: NodeJS.ProcessEnv = process.env
): Promise<boolean> {
  if (!isAccessProtectionEnabled(env)) {
    return true;
  }
  if (!cookieValue) {
    return false;
  }

  const expected = await createAccessCookieValue(getConfiguredAccessPin(env));
  return cookieValue === expected;
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
