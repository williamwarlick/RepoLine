import type { NextRequest } from 'next/server';
import { NextResponse } from 'next/server';
import {
  ACCESS_COOKIE_NAME,
  ACCESS_REDIRECT_PARAM,
  isAccessProtectionEnabled,
  isValidAccessCookie,
  UNLOCK_API_PATH,
  UNLOCK_PATH,
} from '@/lib/access-control';

const PUBLIC_FILE_PATTERN = /\.(?:css|js|map|json|txt|svg|png|jpg|jpeg|gif|webp|ico|woff2?|otf)$/i;
const BLOCKED_HOSTS_ENV_NAME = 'REPOLINE_BLOCKED_HOSTS';

function getBlockedHosts(env: NodeJS.ProcessEnv = process.env): Set<string> {
  return new Set(
    (env[BLOCKED_HOSTS_ENV_NAME] ?? '')
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter(Boolean)
  );
}

function isBypassedPath(pathname: string): boolean {
  return (
    pathname.startsWith('/_next') ||
    pathname === UNLOCK_PATH ||
    pathname === UNLOCK_API_PATH ||
    pathname === '/favicon.ico' ||
    PUBLIC_FILE_PATTERN.test(pathname)
  );
}

export async function middleware(req: NextRequest) {
  const requestHost =
    req.headers.get('x-forwarded-host')?.trim().toLowerCase() ??
    req.headers.get('host')?.trim().toLowerCase() ??
    req.nextUrl.host.trim().toLowerCase();
  if (getBlockedHosts().has(requestHost)) {
    return new NextResponse('Not Found', {
      status: 404,
      headers: {
        'Cache-Control': 'no-store',
        'X-Robots-Tag': 'noindex, nofollow',
      },
    });
  }

  if (!isAccessProtectionEnabled()) {
    return NextResponse.next();
  }

  if (isBypassedPath(req.nextUrl.pathname)) {
    return NextResponse.next();
  }

  const accessCookie = req.cookies.get(ACCESS_COOKIE_NAME)?.value;
  if (await isValidAccessCookie(accessCookie)) {
    return NextResponse.next();
  }

  const loginUrl = req.nextUrl.clone();
  loginUrl.pathname = UNLOCK_PATH;
  loginUrl.searchParams.set(ACCESS_REDIRECT_PARAM, `${req.nextUrl.pathname}${req.nextUrl.search}`);

  return NextResponse.redirect(loginUrl);
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|.*\\..*).*)'],
};
