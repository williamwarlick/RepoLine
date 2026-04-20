'use client';

import { useSessionContext, useTextStream } from '@livekit/components-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  parseRepolineSessionRuntimeEvent,
  REPOLINE_CONTROL_TOPIC,
  REPOLINE_SESSION_STATE_TOPIC,
  type RepolineControlResultEvent,
  type RepolineSessionState,
} from '@/lib/repoline-session-state';

const SESSION_STATE_REFRESH_INTERVAL_MS = 5000;

function newRequestId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function useRepolineSessionRuntime() {
  const session = useSessionContext();
  const { textStreams } = useTextStream(REPOLINE_SESSION_STATE_TOPIC);
  const [runtimeState, setRuntimeState] = useState<RepolineSessionState | undefined>(undefined);
  const [latestControlResult, setLatestControlResult] = useState<
    RepolineControlResultEvent | undefined
  >(undefined);
  const [pendingModelRequestId, setPendingModelRequestId] = useState<string | null>(null);
  const seenEventIdsRef = useRef<Set<string>>(new Set());

  const runtimeEvents = useMemo(() => {
    return textStreams
      .map(parseRepolineSessionRuntimeEvent)
      .filter((event) => event !== null)
      .sort((left, right) => left.timestamp - right.timestamp);
  }, [textStreams]);

  useEffect(() => {
    for (const event of runtimeEvents) {
      if (seenEventIdsRef.current.has(event.id)) {
        continue;
      }
      seenEventIdsRef.current.add(event.id);
      setRuntimeState(event.state);
      if (event.type === 'control_result') {
        setLatestControlResult(event);
        if (event.requestId && event.requestId === pendingModelRequestId) {
          setPendingModelRequestId(null);
        }
      }
    }
  }, [pendingModelRequestId, runtimeEvents]);

  const sendControlMessage = useCallback(
    async (payload: Record<string, unknown>) => {
      await session.room.localParticipant.sendText(JSON.stringify(payload), {
        topic: REPOLINE_CONTROL_TOPIC,
      });
    },
    [session.room.localParticipant]
  );

  const requestRuntimeState = useCallback(async () => {
    if (!session.isConnected) {
      return;
    }

    await sendControlMessage({
      type: 'request_session_state',
      requestId: newRequestId(),
    });
  }, [sendControlMessage, session.isConnected]);

  useEffect(() => {
    if (!session.isConnected) {
      setPendingModelRequestId(null);
      setRuntimeState(undefined);
      setLatestControlResult(undefined);
      seenEventIdsRef.current.clear();
      return;
    }

    void requestRuntimeState();
  }, [requestRuntimeState, session.isConnected]);

  useEffect(() => {
    if (!session.isConnected) {
      return;
    }

    const intervalId = window.setInterval(() => {
      void requestRuntimeState();
    }, SESSION_STATE_REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [requestRuntimeState, session.isConnected]);

  const setRuntimeModel = useCallback(
    async (model: string) => {
      if (!session.isConnected) {
        return;
      }

      const requestId = newRequestId();
      setPendingModelRequestId(requestId);
      try {
        await sendControlMessage({
          type: 'set_model',
          requestId,
          model,
        });
      } catch (error) {
        setPendingModelRequestId(null);
        throw error;
      }
    },
    [sendControlMessage, session.isConnected]
  );

  return {
    runtimeState,
    latestControlResult,
    isUpdatingRuntimeModel: pendingModelRequestId !== null,
    requestRuntimeState,
    setRuntimeModel,
  };
}
