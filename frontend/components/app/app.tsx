'use client';

import type { AppConfig } from '@/app-config';
import { VoiceSessionShell } from '@/components/app/voice-session-shell';

interface AppProps {
  appConfig: AppConfig;
}

export function App({ appConfig }: AppProps) {
  return <VoiceSessionShell appConfig={appConfig} />;
}
