import { NextResponse } from 'next/server';
import {
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

function redirectToUnlock(req: Request, nextPath: string, error: string): NextResponse {
  const url = new URL(UNLOCK_PATH, req.url);
  url.searchParams.set(ACCESS_REDIRECT_PARAM, nextPath);
  url.searchParams.set('error', error);
  return NextResponse.redirect(url);
}

export async function POST(req: Request) {
  if (!isAccessProtectionEnabled()) {
    return NextResponse.redirect(new URL('/', req.url));
  }

  const formData = await req.formData();
  const pin = String(formData.get('pin') ?? '').trim();
  const nextPath = sanitizeNextPath(String(formData.get(ACCESS_REDIRECT_PARAM) ?? '/'));

  if (!pin) {
    return redirectToUnlock(req, nextPath, 'missing_pin');
  }

  const configuredPin = getConfiguredAccessPin();
  if (pin !== configuredPin) {
    return redirectToUnlock(req, nextPath, 'invalid_pin');
  }

  const response = NextResponse.redirect(new URL(nextPath, req.url));
  response.cookies.set(ACCESS_COOKIE_NAME, await createAccessCookieValue(configuredPin), {
    httpOnly: true,
    sameSite: 'lax',
    secure: true,
    path: '/',
    maxAge: 60 * 60 * 12,
  });
  return response;
}

export async function GET() {
  return NextResponse.json(
    { error: `${ACCESS_PIN_ENV_NAME} requires POST` },
    {
      status: 405,
      headers: { Allow: 'POST' },
    }
  );
}
