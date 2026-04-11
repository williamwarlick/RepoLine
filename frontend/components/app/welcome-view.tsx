import { Button } from '@/components/ui/button';

function WelcomeImage() {
  return (
    <div className='mb-5 flex items-center justify-center'>
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src='/repoline-mark.svg'
        alt='RepoLine logo'
        className='size-28 drop-shadow-[0_24px_60px_rgba(43,167,255,0.22)] sm:size-32'
      />
    </div>
  );
}

interface WelcomeViewProps {
  startButtonText: string;
  onStartCall: () => void;
}

export const WelcomeView = ({
  startButtonText,
  onStartCall,
  ref,
}: React.ComponentProps<'div'> & WelcomeViewProps) => {
  return (
    <div ref={ref}>
      <section className='bg-background flex flex-col items-center justify-center text-center'>
        <WelcomeImage />

        <p className='text-foreground max-w-prose pt-1 leading-6 font-medium'>
          Talk to your local coding CLI over voice
        </p>

        <Button
          size='lg'
          onClick={onStartCall}
          className='mt-6 w-64 rounded-full font-mono text-xs font-bold tracking-wider uppercase'
        >
          {startButtonText}
        </Button>
      </section>

      <div className='fixed bottom-5 left-0 flex w-full items-center justify-center'>
        <p className='text-muted-foreground max-w-prose pt-1 text-xs leading-5 font-normal text-pretty md:text-sm'>
          Need help getting set up? Check out the{' '}
          <a
            target='_blank'
            rel='noopener noreferrer'
            href='https://github.com/williamwarlick/RepoLine#quick-start'
            className='underline'
          >
            RepoLine quick start
          </a>
          .
        </p>
      </div>
    </div>
  );
};
