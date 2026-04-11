import type { TextStreamData } from '@livekit/components-react';

export const REPOLINE_UI_ARTIFACT_TOPIC = 'repoline.ui.artifact';

const ATTR = {
  artifactId: 'repoline.artifact_id',
  kind: 'repoline.kind',
  language: 'repoline.language',
  provider: 'repoline.provider',
  sequence: 'repoline.sequence',
  sessionId: 'repoline.session_id',
  title: 'repoline.title',
  turnId: 'repoline.turn_id',
} as const;

export type RepolineArtifactKind = 'tool' | 'code' | 'diff';

export interface RepolineArtifact {
  id: string;
  kind: RepolineArtifactKind;
  language?: string;
  participantIdentity: string;
  provider?: string;
  sequence: number;
  sessionId?: string;
  text: string;
  timestamp: number;
  title: string;
  turnId?: string;
}

export interface RepolineDiffSummary {
  additions: number;
  deletions: number;
  fileCount: number;
  files: string[];
  hunkCount: number;
}

function isArtifactKind(value: string | undefined): value is RepolineArtifactKind {
  return value === 'tool' || value === 'code' || value === 'diff';
}

export function parseRepolineArtifact(textStream: TextStreamData): RepolineArtifact | null {
  const attributes = textStream.streamInfo.attributes ?? {};
  const text = textStream.text.trim();
  const kind = attributes[ATTR.kind];

  if (!text || !isArtifactKind(kind)) {
    return null;
  }

  const title = attributes[ATTR.title]?.trim() || 'Artifact';
  const sequence = Number.parseInt(attributes[ATTR.sequence] ?? '0', 10);

  return {
    id: attributes[ATTR.artifactId] ?? textStream.streamInfo.id,
    kind,
    language: attributes[ATTR.language] || undefined,
    participantIdentity: textStream.participantInfo.identity,
    provider: attributes[ATTR.provider] || undefined,
    sequence: Number.isFinite(sequence) ? sequence : 0,
    sessionId: attributes[ATTR.sessionId] || undefined,
    text,
    timestamp: textStream.streamInfo.timestamp,
    title,
    turnId: attributes[ATTR.turnId] || undefined,
  };
}

export function summarizeRepolineDiff(text: string): RepolineDiffSummary {
  const files = new Set<string>();
  let additions = 0;
  let deletions = 0;
  let hunkCount = 0;

  for (const line of text.split('\n')) {
    if (line.startsWith('diff --git ')) {
      const match = line.match(/^diff --git a\/(.+?) b\/(.+)$/);
      if (match?.[2]) {
        files.add(match[2]);
      }
      continue;
    }

    if (line.startsWith('+++ b/')) {
      files.add(line.slice('+++ b/'.length).trim());
      continue;
    }

    if (line.startsWith('@@')) {
      hunkCount += 1;
      continue;
    }

    if (line.startsWith('+') && !line.startsWith('+++')) {
      additions += 1;
      continue;
    }

    if (line.startsWith('-') && !line.startsWith('---')) {
      deletions += 1;
    }
  }

  return {
    additions,
    deletions,
    fileCount: files.size,
    files: Array.from(files),
    hunkCount,
  };
}

export function formatArtifactProvider(provider?: string): string | null {
  if (!provider) {
    return null;
  }

  if (provider === 'claude') {
    return 'Claude';
  }

  if (provider === 'codex') {
    return 'Codex';
  }

  if (provider === 'cursor') {
    return 'Cursor';
  }

  return provider;
}

export function sortRepolineArtifacts(
  left: Pick<RepolineArtifact, 'id' | 'sequence' | 'timestamp'>,
  right: Pick<RepolineArtifact, 'id' | 'sequence' | 'timestamp'>
): number {
  if (left.timestamp !== right.timestamp) {
    return left.timestamp - right.timestamp;
  }

  if (left.sequence !== right.sequence) {
    return left.sequence - right.sequence;
  }

  return left.id.localeCompare(right.id);
}
