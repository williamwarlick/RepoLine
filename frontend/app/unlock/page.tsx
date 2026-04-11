import { Button } from '@/components/ui/button';
import { ACCESS_REDIRECT_PARAM, sanitizeNextPath } from '@/lib/access-control';

interface UnlockPageProps {
  searchParams?: Promise<Record<string, string | string[] | undefined>>;
}

function getErrorMessage(errorValue: string | undefined): string | null {
  if (errorValue === 'invalid_pin') {
    return 'That PIN was not accepted.';
  }

  if (errorValue === 'missing_pin') {
    return 'Enter the PIN to continue.';
  }

  return null;
}

export default async function UnlockPage({ searchParams }: UnlockPageProps) {
  const resolvedSearchParams = searchParams ? await searchParams : {};
  const nextValue = resolvedSearchParams[ACCESS_REDIRECT_PARAM];
  const errorValue = resolvedSearchParams.error;
  const nextPath = sanitizeNextPath(Array.isArray(nextValue) ? nextValue[0] : nextValue);
  const errorMessage = getErrorMessage(Array.isArray(errorValue) ? errorValue[0] : errorValue);

  return (
    <main className='bg-background flex min-h-svh items-center justify-center px-6 py-10'>
      <section className='bg-card text-card-foreground w-full max-w-md rounded-3xl border p-8 shadow-xl'>
        <div className='space-y-3 text-center'>
          <p className='font-mono text-xs font-bold tracking-[0.2em] uppercase text-zinc-500'>
            Private Access
          </p>
          <h1 className='text-2xl font-semibold tracking-tight'>Enter RepoLine PIN</h1>
          <p className='text-muted-foreground text-sm leading-6'>
            This deployment is private. Enter the access PIN to open the voice session UI.
          </p>
        </div>

        <form action='/api/unlock' method='post' className='mt-8 space-y-4'>
          <input type='hidden' name={ACCESS_REDIRECT_PARAM} value={nextPath} />
          <label className='block space-y-2 text-left'>
            <span className='text-sm font-medium'>PIN</span>
            <input
              name='pin'
              type='password'
              inputMode='numeric'
              autoComplete='one-time-code'
              required
              className='border-input bg-background w-full rounded-2xl border px-4 py-3 text-base outline-none focus-visible:ring-2 focus-visible:ring-emerald-500'
              placeholder='Enter access PIN'
            />
          </label>
          {errorMessage ? (
            <p className='rounded-2xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-700'>
              {errorMessage}
            </p>
          ) : null}
          <Button
            type='submit'
            className='w-full rounded-full font-mono text-xs font-bold tracking-wider uppercase'
          >
            Unlock
          </Button>
        </form>
      </section>
    </main>
  );
}
