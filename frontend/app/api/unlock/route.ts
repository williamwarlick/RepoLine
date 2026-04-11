import { timingSafeEqual } from 'node:crypto';
import { NextResponse } from 'next/server';
import {
  ACCESS_COOKIE_MAX_AGE_SECONDS,
  ACCESS_COOKIE_NAME,
  ACCESS_PIN_ENV_NAME,
  ACCESS_REDIRECT_PARAM,
  createAccessCookieValue,
  getConfiguredAccessPin,
  isAccessProtectionEnabled,
  sanitizeNextPath,
  UNLOCK_PATH,
} from '@/lib/access-control';

export const runtime = 'nodejs';

function buildPrivateHeaders(): Headers {
  return new Headers({
    'Cache-Control': 'no-store',
    'X-Robots-Tag': 'noindex, nofollow',
  });
}

function isAccessCodeMatch(submitted: string, configured: string): boolean {
  const submittedBuffer = Buffer.from(submitted);
  const configuredBuffer = Buffer.from(configured);
  if (submittedBuffer.length !== configuredBuffer.length) {
    return false;
  }

  return timingSafeEqual(submittedBuffer, configuredBuffer);
}

function redirectToUnlock(req: Request, nextPath: string, error: string): NextResponse {
  const url = new URL(UNLOCK_PATH, req.url);
  url.searchParams.set(ACCESS_REDIRECT_PARAM, nextPath);
  url.searchParams.set('error', error);
  return NextResponse.redirect(url, { headers: buildPrivateHeaders() });
}

export async function POST(req: Request) {
  if (!isAccessProtectionEnabled()) {
    return NextResponse.redirect(new URL('/', req.url), { headers: buildPrivateHeaders() });
  }

  const formData = await req.formData();
  const accessCode = String(formData.get('accessCode') ?? formData.get('pin') ?? '').trim();
  const nextPath = sanitizeNextPath(String(formData.get(ACCESS_REDIRECT_PARAM) ?? '/'));

  if (!accessCode) {
    return redirectToUnlock(req, nextPath, 'missing_access_code');
  }

  const configuredPin = getConfiguredAccessPin();
  if (!isAccessCodeMatch(accessCode, configuredPin)) {
    return redirectToUnlock(req, nextPath, 'invalid_access_code');
  }

  const response = NextResponse.redirect(new URL(nextPath, req.url), {
    headers: buildPrivateHeaders(),
  });
  response.cookies.set(ACCESS_COOKIE_NAME, await createAccessCookieValue(configuredPin), {
    httpOnly: true,
    sameSite: 'strict',
    secure: true,
    path: '/',
    maxAge: ACCESS_COOKIE_MAX_AGE_SECONDS,
  });
  return response;
}

export async function GET() {
  return NextResponse.json(
    { error: `${ACCESS_PIN_ENV_NAME} requires POST` },
    {
      status: 405,
      headers: {
        Allow: 'POST',
        'Cache-Control': 'no-store',
        'X-Robots-Tag': 'noindex, nofollow',
      },
    }
  );
}
