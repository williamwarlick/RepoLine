'use client';

import { useTextStream } from '@livekit/components-react';
import { useMemo } from 'react';
import {
  parseRepolineArtifact,
  REPOLINE_UI_ARTIFACT_TOPIC,
  sortRepolineArtifacts,
} from '@/lib/repoline-artifacts';

export function useRepolineArtifacts() {
  const { textStreams } = useTextStream(REPOLINE_UI_ARTIFACT_TOPIC);

  return useMemo(() => {
    return textStreams
      .map(parseRepolineArtifact)
      .filter((artifact) => artifact !== null)
      .sort(sortRepolineArtifacts);
  }, [textStreams]);
}
