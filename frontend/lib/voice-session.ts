import { TokenSource, type TrackPublishOptions } from 'livekit-client';
import type { AppConfig } from '@/app-config';
import { getSandboxTokenSource } from '@/lib/utils';

type VoiceSessionEnv = Readonly<{
  NEXT_PUBLIC_CONN_DETAILS_ENDPOINT?: string;
}>;

export const PRECONNECT_MIC_OPTIONS: TrackPublishOptions = {
  preConnectBuffer: true,
};

export function resolveVoiceSessionMode(
  env: NodeJS.ProcessEnv | VoiceSessionEnv = process.env
): 'sandbox' | 'endpoint' {
  return typeof env.NEXT_PUBLIC_CONN_DETAILS_ENDPOINT === 'string' ? 'sandbox' : 'endpoint';
}

export function createVoiceSessionTokenSource(
  appConfig: AppConfig,
  env: NodeJS.ProcessEnv | VoiceSessionEnv = process.env
) {
  return resolveVoiceSessionMode(env) === 'sandbox'
    ? getSandboxTokenSource(appConfig)
    : TokenSource.endpoint('/api/token');
}
