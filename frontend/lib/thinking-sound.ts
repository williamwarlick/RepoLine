export const THINKING_SOUND_PRESETS = ['off', 'soft-pulse', 'glass'] as const;

export type ThinkingSoundPreset = (typeof THINKING_SOUND_PRESETS)[number];

type ThinkingSoundNote = Readonly<{
  frequency: number;
  offsetMs: number;
  durationMs: number;
  gain: number;
  type: OscillatorType;
  detune?: number;
}>;

type ThinkingSoundDefinition = Readonly<{
  notes: readonly ThinkingSoundNote[];
}>;

export const DEFAULT_THINKING_SOUND_VOLUME = 0.18;
export const DEFAULT_THINKING_SOUND_INTERVAL_MS = 1800;

const MAX_THINKING_SOUND_INTERVAL_MS = 10_000;

const THINKING_SOUND_DEFINITIONS: Record<ThinkingSoundPreset, ThinkingSoundDefinition | null> = {
  off: null,
  'soft-pulse': {
    notes: [
      {
        frequency: 660,
        offsetMs: 0,
        durationMs: 140,
        gain: 0.52,
        type: 'sine',
      },
      {
        frequency: 880,
        offsetMs: 150,
        durationMs: 120,
        gain: 0.32,
        type: 'triangle',
      },
    ],
  },
  glass: {
    notes: [
      {
        frequency: 784,
        offsetMs: 0,
        durationMs: 120,
        gain: 0.4,
        type: 'triangle',
      },
      {
        frequency: 1174,
        offsetMs: 90,
        durationMs: 180,
        gain: 0.26,
        type: 'sine',
        detune: 4,
      },
    ],
  },
};

export function resolveThinkingSoundPreset(
  value: string | undefined,
  fallback: ThinkingSoundPreset = 'off'
): ThinkingSoundPreset {
  const normalized = value?.trim().toLowerCase().replaceAll('_', '-');
  if (!normalized) {
    return fallback;
  }

  return THINKING_SOUND_PRESETS.includes(normalized as ThinkingSoundPreset)
    ? (normalized as ThinkingSoundPreset)
    : fallback;
}

export function clampThinkingSoundVolume(
  value: number | undefined,
  fallback = DEFAULT_THINKING_SOUND_VOLUME
): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }

  const numericValue = value as number;
  return Math.min(1, Math.max(0, numericValue));
}

export function clampThinkingSoundIntervalMs(
  value: number | undefined,
  fallback = DEFAULT_THINKING_SOUND_INTERVAL_MS
): number {
  if (!Number.isFinite(value)) {
    return fallback;
  }

  const numericValue = value as number;
  return Math.round(Math.min(MAX_THINKING_SOUND_INTERVAL_MS, Math.max(0, numericValue)));
}

export function getThinkingSoundDefinition(
  preset: ThinkingSoundPreset
): ThinkingSoundDefinition | null {
  return THINKING_SOUND_DEFINITIONS[preset];
}

export function isThinkingSoundEnabled(preset: ThinkingSoundPreset): boolean {
  return preset !== 'off';
}
