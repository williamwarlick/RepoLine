import { expect, test } from 'bun:test';
import {
  ACCESS_COOKIE_MAX_AGE_SECONDS,
  createAccessCookieValue,
  getConfiguredAccessPin,
  isAccessProtectionEnabled,
  isValidAccessCookie,
} from './access-control';

const ACCESS_CODE = 'test-access-code-123456';

test('access protection is disabled when no secret is configured', async () => {
  expect(isAccessProtectionEnabled({})).toBe(false);
  expect(await isValidAccessCookie(undefined, {})).toBe(true);
});

test('configured access code must be long enough', () => {
  expect(() => getConfiguredAccessPin({ REPOLINE_ACCESS_PIN: 'short' })).toThrow(
    'REPOLINE_ACCESS_PIN must be at least 16 characters'
  );
});

test('signed access cookie is accepted until it expires', async () => {
  const createdAt = 1_000;
  const cookie = await createAccessCookieValue(ACCESS_CODE, createdAt);
  const env = { REPOLINE_ACCESS_PIN: ACCESS_CODE };

  expect(await isValidAccessCookie(cookie, env, createdAt + 1_000)).toBe(true);
  expect(
    await isValidAccessCookie(cookie, env, createdAt + (ACCESS_COOKIE_MAX_AGE_SECONDS - 1) * 1_000)
  ).toBe(true);
  expect(
    await isValidAccessCookie(cookie, env, createdAt + ACCESS_COOKIE_MAX_AGE_SECONDS * 1_000)
  ).toBe(false);
});

test('tampered access cookie is rejected', async () => {
  const cookie = await createAccessCookieValue(ACCESS_CODE);
  const [payload, signature] = cookie.split('.');
  const tamperedSignature = `${signature.slice(0, -1)}${signature.endsWith('A') ? 'B' : 'A'}`;

  expect(
    await isValidAccessCookie(`${payload}.${tamperedSignature}`, {
      REPOLINE_ACCESS_PIN: ACCESS_CODE,
    })
  ).toBe(false);
});
