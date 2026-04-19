import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from 'node:fs';
import { dirname } from 'node:path';

export type PhoneConfig = {
  number: string;
  pin: string;
  dispatchRuleName: string;
  dispatchRuleId: string;
};

export type BridgeProvider = 'claude' | 'codex' | 'cursor' | 'gemini';

export type SetupState = {
  configured_at: string;
  livekit_project_name: string;
  livekit_url: string;
  agent_name: string;
  bridge_provider: BridgeProvider;
  workdir: string;
  phone: PhoneConfig | null;
};

type RawState = {
  configured_at: string;
  livekit_project_name: string;
  livekit_url: string;
  agent_name: string;
  bridge_provider: string;
  workdir: string;
  phone?: {
    number: string;
    pin: string;
    dispatchRuleName?: string;
    dispatchRuleId?: string;
    dispatch_rule_name?: string;
    dispatch_rule_id?: string;
  } | null;
};

export const REPOLINE_SKILL_NAME = 'repoline-voice-session';
export const REPOLINE_TTS_PRONUNCIATION_SKILL_NAME = 'repoline-tts-pronunciation';
export const DEFAULT_CURSOR_MODEL = 'composer-2-fast';
export const DEFAULT_GEMINI_MODEL = 'gemini-2.5-flash';

export function normalizeBridgeProvider(value: string): BridgeProvider {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'codex') {
    return 'codex';
  }
  if (normalized === 'cursor' || normalized === 'cursor-agent') {
    return 'cursor';
  }
  if (normalized === 'gemini') {
    return 'gemini';
  }
  return 'claude';
}

export function buildAgentEnvValues(options: {
  project: { url: string; apiKey: string; apiSecret: string };
  agentName: string;
  bridgeProvider: BridgeProvider;
  workdir: string;
  existingAgentEnv: Record<string, string>;
}): Record<string, string> {
  const sttProvider =
    options.existingAgentEnv.BRIDGE_STT_PROVIDER ??
    (options.existingAgentEnv.DEEPGRAM_API_KEY ? 'deepgram' : 'livekit');
  const ttsProvider =
    options.existingAgentEnv.BRIDGE_TTS_PROVIDER ??
    (options.existingAgentEnv.ELEVENLABS_API_KEY ? 'elevenlabs' : 'livekit');

  return {
    LIVEKIT_URL: options.project.url,
    LIVEKIT_API_KEY: options.project.apiKey,
    LIVEKIT_API_SECRET: options.project.apiSecret,
    LIVEKIT_AGENT_NAME: options.agentName,
    BRIDGE_CLI_PROVIDER: options.bridgeProvider,
    BRIDGE_WORKDIR: options.workdir,
    BRIDGE_MODEL:
      options.existingAgentEnv.BRIDGE_MODEL ??
      (options.bridgeProvider === 'cursor'
        ? DEFAULT_CURSOR_MODEL
        : options.bridgeProvider === 'gemini'
          ? DEFAULT_GEMINI_MODEL
          : ''),
    BRIDGE_CURSOR_TRANSPORT:
      options.existingAgentEnv.BRIDGE_CURSOR_TRANSPORT ?? 'cli',
    BRIDGE_THINKING_LEVEL:
      options.existingAgentEnv.BRIDGE_THINKING_LEVEL ??
      options.existingAgentEnv.BRIDGE_CODEX_REASONING_EFFORT ??
      'low',
    BRIDGE_ACCESS_POLICY: options.existingAgentEnv.BRIDGE_ACCESS_POLICY ?? 'readonly',
    REPOLINE_SKILL_NAME:
      options.existingAgentEnv.REPOLINE_SKILL_NAME ?? REPOLINE_SKILL_NAME,
    REPOLINE_TTS_PRONUNCIATION_SKILL_NAME:
      options.existingAgentEnv.REPOLINE_TTS_PRONUNCIATION_SKILL_NAME ??
      REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    BRIDGE_SYSTEM_PROMPT: options.existingAgentEnv.BRIDGE_SYSTEM_PROMPT ?? '',
    BRIDGE_CHUNK_CHARS: options.existingAgentEnv.BRIDGE_CHUNK_CHARS ?? '80',
    BRIDGE_THINKING_SOUND_PRESET:
      options.existingAgentEnv.BRIDGE_THINKING_SOUND_PRESET ?? 'soft-pulse',
    BRIDGE_THINKING_SOUND_INTERVAL_MS:
      options.existingAgentEnv.BRIDGE_THINKING_SOUND_INTERVAL_MS ?? '1800',
    BRIDGE_THINKING_SOUND_VOLUME:
      options.existingAgentEnv.BRIDGE_THINKING_SOUND_VOLUME ?? '0.11',
    BRIDGE_THINKING_SOUND_SIP_ONLY:
      options.existingAgentEnv.BRIDGE_THINKING_SOUND_SIP_ONLY ?? 'true',
    FINAL_TRANSCRIPT_DEBOUNCE_SECONDS:
      options.existingAgentEnv.FINAL_TRANSCRIPT_DEBOUNCE_SECONDS ?? '0.35',
    BRIDGE_STT_PROVIDER: sttProvider,
    BRIDGE_SHORT_TRANSCRIPT_WORDS:
      options.existingAgentEnv.BRIDGE_SHORT_TRANSCRIPT_WORDS ?? '2',
    BRIDGE_SHORT_TRANSCRIPT_DEBOUNCE_SECONDS:
      options.existingAgentEnv.BRIDGE_SHORT_TRANSCRIPT_DEBOUNCE_SECONDS ?? '0.55',
    LIVEKIT_STT_MODEL: options.existingAgentEnv.LIVEKIT_STT_MODEL ?? 'deepgram/nova-3',
    LIVEKIT_STT_LANGUAGE: options.existingAgentEnv.LIVEKIT_STT_LANGUAGE ?? 'multi',
    DEEPGRAM_API_KEY: options.existingAgentEnv.DEEPGRAM_API_KEY ?? '',
    DEEPGRAM_STT_MODEL: options.existingAgentEnv.DEEPGRAM_STT_MODEL ?? 'nova-3',
    LIVEKIT_TTS_MODEL: options.existingAgentEnv.LIVEKIT_TTS_MODEL ?? 'cartesia/sonic-3',
    BRIDGE_TTS_PROVIDER: ttsProvider,
    LIVEKIT_TTS_VOICE:
      options.existingAgentEnv.LIVEKIT_TTS_VOICE ?? '9626c31c-bec5-4cca-baa8-f8ba9e84c8bc',
    ELEVENLABS_API_KEY: options.existingAgentEnv.ELEVENLABS_API_KEY ?? '',
    ELEVENLABS_TTS_MODEL:
      options.existingAgentEnv.ELEVENLABS_TTS_MODEL ?? 'eleven_flash_v2_5',
    ELEVENLABS_VOICE_ID:
      options.existingAgentEnv.ELEVENLABS_VOICE_ID ??
      options.existingAgentEnv.LIVEKIT_TTS_VOICE ??
      'onwK4e9ZLuTAKqWW03F9',
    LIVEKIT_RECORD_AUDIO: options.existingAgentEnv.LIVEKIT_RECORD_AUDIO ?? 'false',
    LIVEKIT_RECORD_TRACES: options.existingAgentEnv.LIVEKIT_RECORD_TRACES ?? 'false',
    LIVEKIT_RECORD_LOGS: options.existingAgentEnv.LIVEKIT_RECORD_LOGS ?? 'false',
    LIVEKIT_RECORD_TRANSCRIPT:
      options.existingAgentEnv.LIVEKIT_RECORD_TRANSCRIPT ?? 'false',
    REPOLINE_ALLOW_OWNER: options.existingAgentEnv.REPOLINE_ALLOW_OWNER ?? '',
    BRIDGE_PROMETHEUS_PORT: options.existingAgentEnv.BRIDGE_PROMETHEUS_PORT ?? '',
    BRIDGE_GREETING:
      options.existingAgentEnv.BRIDGE_GREETING ??
      'RepoLine is live. What do you want to work on?',
  };
}

export function buildFrontendEnvValues(options: {
  project: { url: string; apiKey: string; apiSecret: string };
  agentName: string;
  existingFrontendEnv: Record<string, string>;
}): Record<string, string> {
  return {
    LIVEKIT_API_KEY: options.project.apiKey,
    LIVEKIT_API_SECRET: options.project.apiSecret,
    LIVEKIT_URL: options.project.url,
    AGENT_NAME: options.agentName,
    NEXT_PUBLIC_APP_URL:
      options.existingFrontendEnv.NEXT_PUBLIC_APP_URL ?? 'http://localhost:3000',
    NEXT_PUBLIC_APP_CONFIG_ENDPOINT:
      options.existingFrontendEnv.NEXT_PUBLIC_APP_CONFIG_ENDPOINT ?? '',
    SANDBOX_ID: options.existingFrontendEnv.SANDBOX_ID ?? '',
  };
}

export function writeBridgeEnvFiles(options: {
  agentEnvPath: string;
  frontendEnvPath: string;
  project: { url: string; apiKey: string; apiSecret: string };
  agentName: string;
  bridgeProvider: BridgeProvider;
  workdir: string;
  existingAgentEnv: Record<string, string>;
  existingFrontendEnv: Record<string, string>;
}): void {
  writeEnvFile(
    options.agentEnvPath,
    buildAgentEnvValues({
      project: options.project,
      agentName: options.agentName,
      bridgeProvider: options.bridgeProvider,
      workdir: options.workdir,
      existingAgentEnv: options.existingAgentEnv,
    })
  );

  writeEnvFile(
    options.frontendEnvPath,
    buildFrontendEnvValues({
      project: options.project,
      agentName: options.agentName,
      existingFrontendEnv: options.existingFrontendEnv,
    })
  );
}

export function writeEnvFile(pathValue: string, values: Record<string, string>): void {
  const lines = ['# Generated by `bun run setup`.', ''];
  for (const [key, value] of Object.entries(values)) {
    lines.push(`${key}=${formatEnvValue(value)}`);
  }
  const nextContents = `${lines.join('\n')}\n`;

  if (existsSync(pathValue)) {
    const currentContents = readFileSync(pathValue, 'utf8');
    if (currentContents === nextContents) {
      return;
    }
    renameSync(pathValue, `${pathValue}.bak`);
  }

  writeFileSync(pathValue, nextContents);
}

export function loadEnvFile(pathValue: string): Record<string, string> {
  if (!existsSync(pathValue)) {
    return {};
  }

  const env: Record<string, string> = {};
  const contents = readFileSync(pathValue, 'utf8');
  for (const line of contents.split(/\r?\n/)) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith('#') || !line.includes('=')) {
      continue;
    }
    const [key, ...rest] = line.split('=');
    let value = rest.join('=').trim();
    if (value.startsWith('"') && value.endsWith('"')) {
      value = value.slice(1, -1).replaceAll('\\"', '"').replaceAll('\\\\', '\\');
    }
    env[key.trim()] = value;
  }
  return env;
}

export function saveSetupState(statePath: string, state: SetupState): void {
  mkdirSync(dirname(statePath), { recursive: true });
  writeFileSync(statePath, `${JSON.stringify(state, null, 2)}\n`);
}

export function loadSetupState(statePath: string): SetupState | null {
  if (!existsSync(statePath)) {
    return null;
  }
  const rawState = JSON.parse(readFileSync(statePath, 'utf8')) as RawState;
  if (
    !rawState.bridge_provider ||
    !rawState.workdir ||
    !rawState.livekit_project_name ||
    !rawState.livekit_url ||
    !rawState.agent_name
  ) {
    throw new Error(
      'existing .bridge/state.json is from the pre-cutover shape; rerun `bun run setup` to regenerate it'
    );
  }
  return {
    configured_at: rawState.configured_at,
    livekit_project_name: rawState.livekit_project_name,
    livekit_url: rawState.livekit_url,
    agent_name: rawState.agent_name,
    bridge_provider: normalizeBridgeProvider(rawState.bridge_provider),
    workdir: rawState.workdir,
    phone: rawState.phone
      ? {
          number: rawState.phone.number,
          pin: rawState.phone.pin,
          dispatchRuleName:
            rawState.phone.dispatchRuleName ?? rawState.phone.dispatch_rule_name ?? '',
          dispatchRuleId: rawState.phone.dispatchRuleId ?? rawState.phone.dispatch_rule_id ?? '',
        }
      : null,
  };
}

function formatEnvValue(value: string): string {
  if (value.length === 0) {
    return '';
  }
  if (/^[A-Za-z0-9_./:@+-]+$/.test(value)) {
    return value;
  }
  return `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`;
}
