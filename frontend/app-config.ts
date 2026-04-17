import {
  clampThinkingSoundIntervalMs,
  clampThinkingSoundVolume,
  resolveThinkingSoundPreset,
  type ThinkingSoundPreset,
} from '@/lib/thinking-sound';

export interface AppConfig {
  pageTitle: string;
  pageDescription: string;
  companyName: string;

  supportsChatInput: boolean;
  supportsVideoInput: boolean;
  supportsScreenShare: boolean;
  isPreConnectBufferEnabled: boolean;

  logo: string;
  startButtonText: string;
  accent?: string;
  logoDark?: string;
  accentDark?: string;

  audioVisualizerType?: 'bar' | 'wave' | 'grid' | 'radial' | 'aura';
  audioVisualizerColor?: `#${string}`;
  audioVisualizerColorDark?: `#${string}`;
  audioVisualizerColorShift?: number;
  audioVisualizerBarCount?: number;
  audioVisualizerGridRowCount?: number;
  audioVisualizerGridColumnCount?: number;
  audioVisualizerRadialBarCount?: number;
  audioVisualizerRadialRadius?: number;
  audioVisualizerWaveLineWidth?: number;
  thinkingSoundPreset?: ThinkingSoundPreset;
  thinkingSoundVolume?: number;
  thinkingSoundIntervalMs?: number;

  // agent dispatch configuration
  agentName?: string;

  // LiveKit Cloud Sandbox configuration
  sandboxId?: string;
}

function readOptionalEnv(key: string): string | undefined {
  return process.env[key]?.trim() || undefined;
}

function readOptionalNumberEnv(key: string): number | undefined {
  const value = readOptionalEnv(key);
  if (!value) {
    return undefined;
  }

  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : undefined;
}

export const APP_CONFIG_DEFAULTS: AppConfig = {
  companyName: 'RepoLine',
  pageTitle: 'RepoLine',
  pageDescription: 'A voice bridge for Claude Code, Codex, Cursor, and other local coding CLIs.',

  supportsChatInput: true,
  supportsVideoInput: false,
  supportsScreenShare: false,
  isPreConnectBufferEnabled: true,

  logo: '/repoline-mark.svg',
  accent: '#22C55E',
  logoDark: '/repoline-mark.svg',
  accentDark: '#67E8F9',
  startButtonText: 'Start voice session',

  // optional: audio visualization configuration
  // audioVisualizerType: 'bar',
  // audioVisualizerColor: '#002cf2',
  // audioVisualizerColorDark: '#1fd5f9',
  // audioVisualizerColorShift: 0.3,
  // audioVisualizerBarCount: 5,
  // audioVisualizerType: 'radial',
  // audioVisualizerRadialBarCount: 24,
  // audioVisualizerRadialRadius: 100,
  // audioVisualizerType: 'grid',
  // audioVisualizerGridRowCount: 25,
  // audioVisualizerGridColumnCount: 25,
  // audioVisualizerType: 'wave',
  // audioVisualizerWaveLineWidth: 3,
  // audioVisualizerType: 'aura',
  thinkingSoundPreset: resolveThinkingSoundPreset(
    readOptionalEnv('THINKING_SOUND_PRESET'),
    process.env.NODE_ENV !== 'production' ? 'soft-pulse' : 'off'
  ),
  thinkingSoundVolume: clampThinkingSoundVolume(readOptionalNumberEnv('THINKING_SOUND_VOLUME')),
  thinkingSoundIntervalMs: clampThinkingSoundIntervalMs(
    readOptionalNumberEnv('THINKING_SOUND_INTERVAL_MS')
  ),

  // agent dispatch configuration
  agentName: readOptionalEnv('AGENT_NAME'),

  // LiveKit Cloud Sandbox configuration
  sandboxId: undefined,
};
