'use client';

import { useSessionContext } from '@livekit/components-react';
import type { PropsWithChildren } from 'react';
import { createContext, useContext } from 'react';
import { PRECONNECT_MIC_OPTIONS } from '@/lib/voice-session';

type VoiceSessionControllerValue = {
  isConnected: boolean;
  startCall: () => Promise<void>;
  endCall: () => void;
};

const VoiceSessionControllerContext = createContext<VoiceSessionControllerValue | null>(null);

export function VoiceSessionControllerProvider({ children }: PropsWithChildren) {
  const { isConnected, start, end } = useSessionContext();

  return (
    <VoiceSessionControllerContext.Provider
      value={{
        isConnected,
        startCall: () =>
          start({
            tracks: {
              microphone: {
                enabled: true,
                publishOptions: PRECONNECT_MIC_OPTIONS,
              },
            },
          }),
        endCall: () => {
          end();
        },
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
