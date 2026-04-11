'use client';

import * as Collapsible from '@radix-ui/react-collapsible';
import { ChevronRightIcon, Code2Icon, FileDiffIcon, WrenchIcon } from 'lucide-react';
import { useMemo, useState } from 'react';
import {
  formatArtifactProvider,
  type RepolineArtifact,
  summarizeRepolineDiff,
} from '@/lib/repoline-artifacts';
import { cn } from '@/lib/shadcn/utils';

interface RepolineArtifactCardProps {
  artifact: RepolineArtifact;
}

function artifactIcon(kind: RepolineArtifact['kind']) {
  if (kind === 'tool') {
    return WrenchIcon;
  }

  if (kind === 'diff') {
    return FileDiffIcon;
  }

  return Code2Icon;
}

function artifactLabel(kind: RepolineArtifact['kind']) {
  if (kind === 'tool') {
    return 'Tool';
  }

  if (kind === 'diff') {
    return 'Diff';
  }

  return 'Code';
}

function lineClassName(line: string, kind: RepolineArtifact['kind']) {
  return kind === 'tool' ? 'text-cyan-100' : 'text-foreground/90';
}

export function RepolineArtifactCard({ artifact }: RepolineArtifactCardProps) {
  const [open, setOpen] = useState(false);
  const Icon = artifactIcon(artifact.kind);
  const lines = useMemo(() => artifact.text.split('\n'), [artifact.text]);
  const lineCount = lines.length;
  const providerLabel = formatArtifactProvider(artifact.provider);
  const diffSummary = useMemo(() => {
    if (artifact.kind !== 'diff') {
      return null;
    }

    return summarizeRepolineDiff(artifact.text);
  }, [artifact.kind, artifact.text]);
  const preview = useMemo(() => {
    if (artifact.kind === 'diff' && diffSummary) {
      const filePreview = diffSummary.files.slice(0, 2).join(', ');
      if (filePreview) {
        return `${diffSummary.fileCount} file${diffSummary.fileCount === 1 ? '' : 's'} changed: ${filePreview}`;
      }

      return 'Diff summary available.';
    }

    return (
      lines
        .map((line) => line.trim())
        .find(Boolean)
        ?.slice(0, 140) ?? 'No preview available.'
    );
  }, [artifact.kind, diffSummary, lines]);

  const metadataBadges = (
    <>
      <span className='rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] uppercase tracking-[0.14em] text-white/60'>
        {artifactLabel(artifact.kind)}
      </span>
      {providerLabel && (
        <span className='rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/55'>
          {providerLabel}
        </span>
      )}
      {artifact.language && artifact.kind !== 'diff' && (
        <span className='rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/55'>
          {artifact.language}
        </span>
      )}
      <span className='rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[11px] text-white/45'>
        {lineCount} lines
      </span>
    </>
  );

  if (artifact.kind === 'diff' && diffSummary) {
    return (
      <div className='w-full rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm'>
        <div className='flex w-full items-start gap-3 p-3 text-left'>
          <span className='mt-0.5 rounded-xl border border-white/10 bg-white/5 p-2 text-cyan-100'>
            <Icon className='size-4' />
          </span>
          <span className='min-w-0 flex-1'>
            <span className='flex flex-wrap items-center gap-2'>
              <span className='text-sm font-medium text-white'>{artifact.title}</span>
              {metadataBadges}
            </span>
            <span className='mt-1 block text-xs text-white/50'>{preview}</span>
          </span>
        </div>

        <div className='border-t border-white/10 px-3 py-2'>
          <div className='flex flex-wrap items-center gap-2 text-[11px] text-white/55'>
            <span className='rounded-full border border-white/10 bg-black/20 px-2 py-1'>
              {diffSummary.fileCount} file{diffSummary.fileCount === 1 ? '' : 's'}
            </span>
            <span className='rounded-full border border-emerald-400/15 bg-emerald-500/10 px-2 py-1 text-emerald-100'>
              +{diffSummary.additions} additions
            </span>
            <span className='rounded-full border border-rose-400/15 bg-rose-500/10 px-2 py-1 text-rose-100'>
              -{diffSummary.deletions} deletions
            </span>
            <span className='rounded-full border border-white/10 bg-black/20 px-2 py-1'>
              {diffSummary.hunkCount} hunk{diffSummary.hunkCount === 1 ? '' : 's'}
            </span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <Collapsible.Root
      className='w-full rounded-2xl border border-white/10 bg-white/5 backdrop-blur-sm'
      onOpenChange={setOpen}
      open={open}
    >
      <Collapsible.Trigger asChild>
        <button
          className='flex w-full items-start gap-3 p-3 text-left transition-colors hover:bg-white/5'
          type='button'
        >
          <span className='mt-0.5 rounded-xl border border-white/10 bg-white/5 p-2 text-cyan-100'>
            <Icon className='size-4' />
          </span>
          <span className='min-w-0 flex-1'>
            <span className='flex flex-wrap items-center gap-2'>
              <span className='text-sm font-medium text-white'>{artifact.title}</span>
              {metadataBadges}
            </span>
            <span className='mt-1 block text-xs text-white/50'>{preview}</span>
          </span>
          <ChevronRightIcon
            className={cn(
              'mt-1 size-4 shrink-0 text-white/45 transition-transform',
              open && 'rotate-90'
            )}
          />
        </button>
      </Collapsible.Trigger>

      <Collapsible.Content className='px-3 pb-3'>
        <div className='max-h-80 overflow-auto rounded-xl border border-white/10 bg-black/40 p-3'>
          <div className='min-w-fit font-mono text-[12px] leading-5'>
            {lines.map((line, index) => (
              <div
                className={cn('whitespace-pre px-2', lineClassName(line, artifact.kind))}
                key={`${artifact.id}-${index}`}
              >
                {line || ' '}
              </div>
            ))}
          </div>
        </div>
      </Collapsible.Content>
    </Collapsible.Root>
  );
}
