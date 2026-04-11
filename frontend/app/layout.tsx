import type { Metadata } from 'next';
import { Public_Sans } from 'next/font/google';
import localFont from 'next/font/local';
import { headers } from 'next/headers';
import { ThemeProvider } from '@/components/app/theme-provider';
import { ThemeToggle } from '@/components/app/theme-toggle';
import { cn } from '@/lib/shadcn/utils';
import { getAppConfig, getStyles } from '@/lib/utils';
import '@/styles/globals.css';

const publicSans = Public_Sans({
  variable: '--font-public-sans',
  subsets: ['latin'],
});

const commitMono = localFont({
  display: 'swap',
  variable: '--font-commit-mono',
  src: [
    {
      path: '../fonts/CommitMono-400-Regular.otf',
      weight: '400',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-700-Regular.otf',
      weight: '700',
      style: 'normal',
    },
    {
      path: '../fonts/CommitMono-400-Italic.otf',
      weight: '400',
      style: 'italic',
    },
    {
      path: '../fonts/CommitMono-700-Italic.otf',
      weight: '700',
      style: 'italic',
    },
  ],
});

const DEFAULT_APP_BASE_URL = 'http://localhost:3000';

function getMetadataBase(): URL {
  const baseUrl =
    process.env.NEXT_PUBLIC_APP_URL ||
    (process.env.VERCEL_URL ? `https://${process.env.VERCEL_URL}` : DEFAULT_APP_BASE_URL);

  try {
    return new URL(baseUrl);
  } catch {
    return new URL(DEFAULT_APP_BASE_URL);
  }
}

interface RootLayoutProps {
  children: React.ReactNode;
}

export async function generateMetadata(): Promise<Metadata> {
  const hdrs = await headers();
  const appConfig = await getAppConfig(hdrs);

  return {
    metadataBase: getMetadataBase(),
    title: appConfig.pageTitle,
    description: appConfig.pageDescription,
    openGraph: {
      title: appConfig.pageTitle,
      description: appConfig.pageDescription,
      images: ['/opengraph-image'],
    },
    twitter: {
      card: 'summary_large_image',
      title: appConfig.pageTitle,
      description: appConfig.pageDescription,
      images: ['/opengraph-image'],
    },
  };
}

export default async function RootLayout({ children }: RootLayoutProps) {
  const hdrs = await headers();
  const appConfig = await getAppConfig(hdrs);
  const styles = getStyles(appConfig);
  const { companyName, logo, logoDark } = appConfig;

  return (
    <html
      lang='en'
      suppressHydrationWarning
      className={cn(
        publicSans.variable,
        commitMono.variable,
        'scroll-smooth font-sans antialiased'
      )}
    >
      <head>{styles && <style>{styles}</style>}</head>
      <body suppressHydrationWarning className='overflow-x-hidden'>
        <ThemeProvider
          attribute='class'
          defaultTheme='system'
          enableSystem
          disableTransitionOnChange
        >
          <header className='fixed top-0 left-0 z-50 hidden w-full flex-row justify-between p-6 md:flex'>
            <a
              target='_blank'
              rel='noopener noreferrer'
              href='https://github.com/williamwarlick/RepoLine'
              className='scale-100 transition-transform duration-300 hover:scale-110'
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={logo} alt={`${companyName} Logo`} className='block size-6 dark:hidden' />
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={logoDark ?? logo}
                alt={`${companyName} Logo`}
                className='hidden size-6 dark:block'
              />
            </a>
            <span className='text-foreground font-mono text-xs font-bold tracking-wider uppercase'>
              Built with{' '}
              <a
                target='_blank'
                rel='noopener noreferrer'
                href='https://docs.livekit.io/agents'
                className='underline underline-offset-4'
              >
                LiveKit Agents
              </a>
            </span>
          </header>

          {children}
          <div className='group fixed bottom-0 left-1/2 z-50 mb-2 -translate-x-1/2'>
            <ThemeToggle className='translate-y-20 transition-transform delay-150 duration-300 group-hover:translate-y-0' />
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
