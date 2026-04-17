'use client';

import { useVoiceAssistant } from '@livekit/components-react';
import { useEffect, useMemo, useRef } from 'react';
import {
  clampThinkingSoundIntervalMs,
  clampThinkingSoundVolume,
  getThinkingSoundDefinition,
  isThinkingSoundEnabled,
  resolveThinkingSoundPreset,
  type ThinkingSoundPreset,
} from '@/lib/thinking-sound';

type ThinkingSoundControllerProps = {
  preset?: ThinkingSoundPreset | string;
  volume?: number;
  intervalMs?: number;
};

export function ThinkingSoundController({
  preset: presetValue,
  volume,
  intervalMs,
}: ThinkingSoundControllerProps) {
  const { state } = useVoiceAssistant();
  const audioContextRef = useRef<AudioContext | null>(null);
  const timeoutRef = useRef<number | null>(null);
  const activeOscillatorsRef = useRef<OscillatorNode[]>([]);
  const activeGainNodesRef = useRef<GainNode[]>([]);

  const preset = useMemo(() => resolveThinkingSoundPreset(presetValue), [presetValue]);
  const normalizedVolume = useMemo(() => clampThinkingSoundVolume(volume), [volume]);
  const normalizedIntervalMs = useMemo(
    () => clampThinkingSoundIntervalMs(intervalMs),
    [intervalMs]
  );

  useEffect(() => {
    return () => {
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
      }
      stopActiveCue(activeOscillatorsRef.current, activeGainNodesRef.current);
      activeOscillatorsRef.current = [];
      activeGainNodesRef.current = [];

      if (audioContextRef.current) {
        void audioContextRef.current.close();
        audioContextRef.current = null;
      }
    };
  }, []);

  useEffect(() => {
    if (timeoutRef.current !== null) {
      window.clearTimeout(timeoutRef.current);
      timeoutRef.current = null;
    }

    stopActiveCue(activeOscillatorsRef.current, activeGainNodesRef.current);
    activeOscillatorsRef.current = [];
    activeGainNodesRef.current = [];

    if (state !== 'thinking' || !isThinkingSoundEnabled(preset)) {
      return;
    }

    let cancelled = false;

    const playAndSchedule = async () => {
      if (cancelled) {
        return;
      }

      const activeCue = await playThinkingCue({
        preset,
        volume: normalizedVolume,
        existingContext: audioContextRef.current,
      });

      if (activeCue.context) {
        audioContextRef.current = activeCue.context;
      }
      activeOscillatorsRef.current = activeCue.oscillators;
      activeGainNodesRef.current = activeCue.gains;

      if (cancelled || normalizedIntervalMs <= 0) {
        return;
      }

      timeoutRef.current = window.setTimeout(() => {
        void playAndSchedule();
      }, normalizedIntervalMs);
    };

    void playAndSchedule();

    return () => {
      cancelled = true;
      if (timeoutRef.current !== null) {
        window.clearTimeout(timeoutRef.current);
        timeoutRef.current = null;
      }
      stopActiveCue(activeOscillatorsRef.current, activeGainNodesRef.current);
      activeOscillatorsRef.current = [];
      activeGainNodesRef.current = [];
    };
  }, [normalizedIntervalMs, normalizedVolume, preset, state]);

  return null;
}

async function playThinkingCue({
  preset,
  volume,
  existingContext,
}: {
  preset: ThinkingSoundPreset;
  volume: number;
  existingContext: AudioContext | null;
}) {
  const definition = getThinkingSoundDefinition(preset);
  if (!definition || typeof window === 'undefined' || typeof window.AudioContext === 'undefined') {
    return {
      context: existingContext,
      oscillators: [],
      gains: [],
    };
  }

  const context = existingContext ?? new window.AudioContext();
  if (context.state === 'suspended') {
    try {
      await context.resume();
    } catch {
      return {
        context,
        oscillators: [],
        gains: [],
      };
    }
  }

  const now = context.currentTime;
  const oscillators: OscillatorNode[] = [];
  const gains: GainNode[] = [];

  for (const note of definition.notes) {
    const oscillator = context.createOscillator();
    const gain = context.createGain();

    const startAt = now + note.offsetMs / 1000;
    const endAt = startAt + note.durationMs / 1000;
    const attackEndAt = startAt + Math.min(note.durationMs * 0.35, 45) / 1000;
    const sustainAt = startAt + (note.durationMs * 0.72) / 1000;
    const peakGain = Math.max(note.gain * volume, 0.0001);

    oscillator.type = note.type;
    oscillator.frequency.value = note.frequency;
    if (typeof note.detune === 'number') {
      oscillator.detune.value = note.detune;
    }

    gain.gain.setValueAtTime(0.0001, startAt);
    gain.gain.exponentialRampToValueAtTime(peakGain, attackEndAt);
    gain.gain.exponentialRampToValueAtTime(Math.max(peakGain * 0.5, 0.0001), sustainAt);
    gain.gain.exponentialRampToValueAtTime(0.0001, endAt);

    oscillator.connect(gain);
    gain.connect(context.destination);

    oscillator.start(startAt);
    oscillator.stop(endAt + 0.03);

    oscillators.push(oscillator);
    gains.push(gain);
  }

  return {
    context,
    oscillators,
    gains,
  };
}

function stopActiveCue(oscillators: readonly OscillatorNode[], gains: readonly GainNode[]) {
  for (const oscillator of oscillators) {
    try {
      oscillator.stop();
    } catch {
      // The cue may already be finished by the time the state changes.
    }
    oscillator.disconnect();
  }

  for (const gain of gains) {
    gain.disconnect();
  }
}
