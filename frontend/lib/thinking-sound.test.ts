import { describe, expect, it } from 'bun:test';
import {
  clampThinkingSoundIntervalMs,
  clampThinkingSoundVolume,
  DEFAULT_THINKING_SOUND_INTERVAL_MS,
  DEFAULT_THINKING_SOUND_VOLUME,
  getThinkingSoundDefinition,
  resolveThinkingSoundPreset,
} from '@/lib/thinking-sound';

describe('thinking sound helpers', () => {
  it('accepts supported preset names and normalizes separators', () => {
    expect(resolveThinkingSoundPreset('soft-pulse')).toBe('soft-pulse');
    expect(resolveThinkingSoundPreset('soft_pulse')).toBe('soft-pulse');
    expect(resolveThinkingSoundPreset('glass')).toBe('glass');
  });

  it('falls back when the preset is unsupported or absent', () => {
    expect(resolveThinkingSoundPreset(undefined, 'glass')).toBe('glass');
    expect(resolveThinkingSoundPreset('unknown-sound', 'soft-pulse')).toBe('soft-pulse');
  });

  it('clamps volume into the browser-safe range', () => {
    expect(clampThinkingSoundVolume(undefined)).toBe(DEFAULT_THINKING_SOUND_VOLUME);
    expect(clampThinkingSoundVolume(-1)).toBe(0);
    expect(clampThinkingSoundVolume(2)).toBe(1);
    expect(clampThinkingSoundVolume(0.42)).toBe(0.42);
  });

  it('clamps repeat intervals and allows one-shot playback', () => {
    expect(clampThinkingSoundIntervalMs(undefined)).toBe(DEFAULT_THINKING_SOUND_INTERVAL_MS);
    expect(clampThinkingSoundIntervalMs(-50)).toBe(0);
    expect(clampThinkingSoundIntervalMs(0)).toBe(0);
    expect(clampThinkingSoundIntervalMs(14_500)).toBe(10_000);
  });

  it('exposes cue definitions only for enabled presets', () => {
    expect(getThinkingSoundDefinition('off')).toBeNull();
    expect(getThinkingSoundDefinition('soft-pulse')?.notes.length).toBeGreaterThan(0);
    expect(getThinkingSoundDefinition('glass')?.notes.length).toBeGreaterThan(0);
  });
});
