'use client';

import type { AgentState, ReceivedMessage } from '@livekit/components-react';
import { AnimatePresence } from 'motion/react';
import { type ComponentProps, useMemo } from 'react';
import { AgentChatIndicator } from '@/components/agents-ui/agent-chat-indicator';
import { RepolineArtifactCard } from '@/components/agents-ui/repoline-artifact-card';
import {
  Conversation,
  ConversationContent,
  ConversationScrollButton,
} from '@/components/ai-elements/conversation';
import { Message, MessageContent, MessageResponse } from '@/components/ai-elements/message';
import { useRepolineArtifacts } from '@/hooks/useRepolineArtifacts';

/**
 * Props for the AgentChatTranscript component.
 */
export interface AgentChatTranscriptProps extends ComponentProps<'div'> {
  /**
   * The current state of the agent. When 'thinking', displays a loading indicator.
   */
  agentState?: AgentState;
  /**
   * Array of messages to display in the transcript.
   * @defaultValue []
   */
  messages?: ReceivedMessage[];
  /**
   * Additional CSS class names to apply to the conversation container.
   */
  className?: string;
}

/**
 * A chat transcript component that displays a conversation between the user and agent.
 * Shows messages with timestamps and origin indicators, plus a thinking indicator
 * when the agent is processing.
 *
 * @extends ComponentProps<'div'>
 *
 * @example
 * ```tsx
 * <AgentChatTranscript
 *   agentState={agentState}
 *   messages={chatMessages}
 * />
 * ```
 */
export function AgentChatTranscript({
  agentState,
  messages = [],
  className,
  ...props
}: AgentChatTranscriptProps) {
  const artifacts = useRepolineArtifacts();
  const timeline = useMemo(() => {
    const messageEntries = messages.map((message, index) => ({
      index,
      kind: 'message' as const,
      sortKey: `${message.timestamp}-${index}-message`,
      timestamp: message.timestamp,
      value: message,
    }));
    const artifactEntries = artifacts.map((artifact, index) => ({
      index,
      kind: 'artifact' as const,
      sortKey: `${artifact.timestamp}-${artifact.sequence}-${index}-artifact`,
      timestamp: artifact.timestamp,
      value: artifact,
    }));

    return [...messageEntries, ...artifactEntries].sort((left, right) => {
      if (left.timestamp !== right.timestamp) {
        return left.timestamp - right.timestamp;
      }

      return left.sortKey.localeCompare(right.sortKey);
    });
  }, [artifacts, messages]);

  return (
    <Conversation className={className} {...props}>
      <ConversationContent>
        {timeline.map((entry) => {
          if (entry.kind === 'artifact') {
            return (
              <Message from='assistant' key={entry.value.id}>
                <MessageContent className='w-full max-w-full rounded-none bg-transparent p-0'>
                  <RepolineArtifactCard artifact={entry.value} />
                </MessageContent>
              </Message>
            );
          }

          const { id, timestamp, from, message } = entry.value;
          const locale = navigator?.language ?? 'en-US';
          const messageOrigin = from?.isLocal ? 'user' : 'assistant';
          const time = new Date(timestamp);
          const title = time.toLocaleTimeString(locale, { timeStyle: 'full' });

          return (
            <Message key={id} title={title} from={messageOrigin}>
              <MessageContent>
                <MessageResponse>{message}</MessageResponse>
              </MessageContent>
            </Message>
          );
        })}
        <AnimatePresence>
          {agentState === 'thinking' && <AgentChatIndicator size='sm' />}
        </AnimatePresence>
      </ConversationContent>
      <ConversationScrollButton />
    </Conversation>
  );
}
