'use client';

import { ArrowDownIcon } from 'lucide-react';
import type { ComponentProps, RefObject } from 'react';
import {
  createContext,
  useCallback,
  useContext,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

const STICK_TO_BOTTOM_THRESHOLD_PX = 72;

interface ConversationContextValue {
  contentRef: RefObject<HTMLDivElement | null>;
  isAtBottom: boolean;
  scrollRef: RefObject<HTMLDivElement | null>;
  scrollToBottom: (behavior?: ScrollBehavior) => void;
}

const ConversationContext = createContext<ConversationContextValue | null>(null);

function useConversationContext() {
  const context = useContext(ConversationContext);

  if (!context) {
    throw new Error('Conversation components must be used within Conversation');
  }

  return context;
}

export type ConversationProps = ComponentProps<'div'>;

export const Conversation = ({ children, className, role, ...props }: ConversationProps) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const contentRef = useRef<HTMLDivElement>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const shouldStickRef = useRef(true);

  const syncScrollState = useCallback(() => {
    const scrollElement = scrollRef.current;

    if (!scrollElement) {
      return;
    }

    const distanceFromBottom =
      scrollElement.scrollHeight - scrollElement.scrollTop - scrollElement.clientHeight;
    const nextIsAtBottom = distanceFromBottom <= STICK_TO_BOTTOM_THRESHOLD_PX;

    shouldStickRef.current = nextIsAtBottom;
    setIsAtBottom(nextIsAtBottom);
  }, []);

  const scrollToBottom = useCallback((behavior: ScrollBehavior = 'smooth') => {
    const scrollElement = scrollRef.current;

    if (!scrollElement) {
      return;
    }

    shouldStickRef.current = true;
    setIsAtBottom(true);
    scrollElement.scrollTo({
      top: scrollElement.scrollHeight,
      behavior,
    });
  }, []);

  useLayoutEffect(() => {
    const scrollElement = scrollRef.current;

    if (!scrollElement) {
      return;
    }

    syncScrollState();

    const handleScroll = () => {
      syncScrollState();
    };

    scrollElement.addEventListener('scroll', handleScroll, { passive: true });

    return () => {
      scrollElement.removeEventListener('scroll', handleScroll);
    };
  }, [syncScrollState]);

  useLayoutEffect(() => {
    const scrollElement = scrollRef.current;
    const contentElement = contentRef.current;

    if (!scrollElement || !contentElement) {
      return;
    }

    let frame = 0;

    const syncContentResize = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (shouldStickRef.current) {
          scrollElement.scrollTop = scrollElement.scrollHeight;
        }

        syncScrollState();
      });
    };

    syncContentResize();

    const resizeObserver = new ResizeObserver(() => {
      syncContentResize();
    });

    resizeObserver.observe(contentElement);

    return () => {
      cancelAnimationFrame(frame);
      resizeObserver.disconnect();
    };
  }, [syncScrollState]);

  const contextValue = useMemo(
    () => ({
      contentRef,
      isAtBottom,
      scrollRef,
      scrollToBottom,
    }),
    [isAtBottom, scrollToBottom]
  );

  return (
    <ConversationContext.Provider value={contextValue}>
      <div
        className={cn('relative flex-1 min-h-0 overflow-hidden', className)}
        role={role ?? 'log'}
        {...props}
      >
        {children}
      </div>
    </ConversationContext.Provider>
  );
};

export type ConversationContentProps = ComponentProps<'div'> & {
  scrollClassName?: string;
};

export const ConversationContent = ({
  className,
  scrollClassName,
  ...props
}: ConversationContentProps) => {
  const { contentRef, scrollRef } = useConversationContext();

  return (
    <div
      className={cn(
        'size-full overflow-x-hidden overflow-y-auto overscroll-contain touch-pan-y [scrollbar-gutter:stable_both-edges]',
        scrollClassName
      )}
      data-transcript-scrollable='true'
      ref={scrollRef}
    >
      <div
        className={cn('flex min-h-full flex-col gap-8 p-4', className)}
        ref={contentRef}
        {...props}
      />
    </div>
  );
};

export type ConversationEmptyStateProps = ComponentProps<'div'> & {
  title?: string;
  description?: string;
  icon?: React.ReactNode;
};

export const ConversationEmptyState = ({
  className,
  title = 'No messages yet',
  description = 'Start a conversation to see messages here',
  icon,
  children,
  ...props
}: ConversationEmptyStateProps) => (
  <div
    className={cn(
      'flex size-full flex-col items-center justify-center gap-3 p-8 text-center',
      className
    )}
    {...props}
  >
    {children ?? (
      <>
        {icon && <div className='text-muted-foreground'>{icon}</div>}
        <div className='space-y-1'>
          <h3 className='text-sm font-medium'>{title}</h3>
          {description && <p className='text-muted-foreground text-sm'>{description}</p>}
        </div>
      </>
    )}
  </div>
);

export type ConversationScrollButtonProps = ComponentProps<typeof Button>;

export const ConversationScrollButton = ({
  className,
  ...props
}: ConversationScrollButtonProps) => {
  const { isAtBottom, scrollToBottom } = useConversationContext();

  const handleScrollToBottom = useCallback(() => {
    scrollToBottom();
  }, [scrollToBottom]);

  return (
    !isAtBottom && (
      <Button
        className={cn('absolute bottom-4 left-[50%] translate-x-[-50%] rounded-full', className)}
        onClick={handleScrollToBottom}
        size='icon'
        type='button'
        variant='outline'
        {...props}
      >
        <ArrowDownIcon className='size-4' />
      </Button>
    )
  );
};
