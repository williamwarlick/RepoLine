'use client';

import { useSessionContext } from '@livekit/components-react';
import type { PropsWithChildren } from 'react';
import { createContext, useContext } from 'react';
import { useRepolineSessionRuntime } from '@/hooks/useRepolineSessionRuntime';
import type {
  RepolineControlResultEvent,
  RepolineSessionState,
} from '@/lib/repoline-session-state';
import { PRECONNECT_MIC_OPTIONS } from '@/lib/voice-session';

type VoiceSessionControllerValue = {
  isConnected: boolean;
  startCall: () => Promise<void>;
  endCall: () => void;
  runtimeState?: RepolineSessionState;
  latestControlResult?: RepolineControlResultEvent;
  isUpdatingRuntimeModel: boolean;
  setRuntimeModel: (model: string) => Promise<void>;
};

const VoiceSessionControllerContext = createContext<VoiceSessionControllerValue | null>(null);

export function VoiceSessionControllerProvider({ children }: PropsWithChildren) {
  const session = useSessionContext();
  const { isConnected, start, end, room } = session;
  const { runtimeState, latestControlResult, isUpdatingRuntimeModel, setRuntimeModel } =
    useRepolineSessionRuntime();

  async function startCall() {
    await start({
      tracks: {
        microphone: {
          enabled: false,
        },
      },
    });

    await room.localParticipant.setMicrophoneEnabled(true, undefined, PRECONNECT_MIC_OPTIONS);
  }

  return (
    <VoiceSessionControllerContext.Provider
      value={{
        isConnected,
        startCall,
        endCall: () => {
          end();
        },
        runtimeState,
        latestControlResult,
        isUpdatingRuntimeModel,
        setRuntimeModel,
      }}
    >
      {children}
    </VoiceSessionControllerContext.Provider>
  );
}

export function useVoiceSessionController(): VoiceSessionControllerValue {
  const value = useContext(VoiceSessionControllerContext);
  if (!value) {
    throw new Error('useVoiceSessionController must be used within VoiceSessionShell');
  }
  return value;
}
