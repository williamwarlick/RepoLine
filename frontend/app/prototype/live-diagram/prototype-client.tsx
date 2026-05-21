'use client';

import {
  ArrowLeftIcon,
  ArrowRightIcon,
  BotIcon,
  CheckCircle2Icon,
  Clock3Icon,
  Code2Icon,
  GitBranchIcon,
  Maximize2Icon,
  MessageSquareTextIcon,
  PanelRightIcon,
  RotateCcwIcon,
  SparklesIcon,
} from 'lucide-react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/shadcn/utils';

// PROTOTYPE: Three variants of the live diagram artifact experience, switchable via
// `?variant=`, on the throwaway `/prototype/live-diagram` route.

type VariantKey = 'A' | 'B' | 'C';

type DiagramRevision = {
  id: string;
  title: string;
  agentNote: string;
  source: string;
  nodes: Array<{ id: string; label: string; detail: string; tone: 'voice' | 'agent' | 'artifact' }>;
  edges: Array<[string, string]>;
};

const VARIANTS: Array<{ key: VariantKey; name: string }> = [
  { key: 'A', name: 'Transcript card' },
  { key: 'B', name: 'Split studio' },
  { key: 'C', name: 'Review board' },
];

const REVISIONS: DiagramRevision[] = [
  {
    id: 'rev-1',
    title: 'Initial live diagram',
    agentNote:
      'I started with the voice turn and made the diagram artifact the shared visual object.',
    source: `flowchart LR
  VoiceTurn["Voice turn"]
  AgentEdit["Agent edits Mermaid"]
  BrowserArtifact["Browser companion renders artifact"]
  VoiceTurn --> AgentEdit --> BrowserArtifact`,
    nodes: [
      {
        id: 'VoiceTurn',
        label: 'Voice turn',
        detail: 'User describes the workflow.',
        tone: 'voice',
      },
      {
        id: 'AgentEdit',
        label: 'Agent edit',
        detail: 'Agent rewrites Mermaid source.',
        tone: 'agent',
      },
      {
        id: 'BrowserArtifact',
        label: 'Browser artifact',
        detail: 'Rendered diagram stays visible.',
        tone: 'artifact',
      },
    ],
    edges: [
      ['VoiceTurn', 'AgentEdit'],
      ['AgentEdit', 'BrowserArtifact'],
    ],
  },
  {
    id: 'rev-2',
    title: 'Adds inspectable source',
    agentNote:
      'I added source visibility because the artifact should be reviewable, not just pretty.',
    source: `flowchart LR
  VoiceTurn["Voice turn"]
  AgentEdit["Agent edits Mermaid"]
  SourcePane["Inspectable source"]
  BrowserArtifact["Rendered diagram"]
  VoiceTurn --> AgentEdit
  AgentEdit --> SourcePane
  SourcePane --> BrowserArtifact`,
    nodes: [
      {
        id: 'VoiceTurn',
        label: 'Voice turn',
        detail: 'User describes a system shape.',
        tone: 'voice',
      },
      {
        id: 'AgentEdit',
        label: 'Agent edit',
        detail: 'Agent publishes a new revision.',
        tone: 'agent',
      },
      {
        id: 'SourcePane',
        label: 'Source pane',
        detail: 'Mermaid stays visible.',
        tone: 'artifact',
      },
      {
        id: 'BrowserArtifact',
        label: 'Rendered diagram',
        detail: 'Visual updates in place.',
        tone: 'artifact',
      },
    ],
    edges: [
      ['VoiceTurn', 'AgentEdit'],
      ['AgentEdit', 'SourcePane'],
      ['SourcePane', 'BrowserArtifact'],
    ],
  },
  {
    id: 'rev-3',
    title: 'Adds approval boundary',
    agentNote:
      'I separated diagram changes from repo mutation so a visual update never implies code approval.',
    source: `flowchart LR
  VoiceTurn["Voice turn"]
  AgentEdit["Agent edits Mermaid"]
  LiveArtifact["Live Diagram Artifact"]
  Approval["Approval checkpoint"]
  RepoMutation["Repo mutation"]
  VoiceTurn --> AgentEdit --> LiveArtifact
  LiveArtifact --> Approval --> RepoMutation`,
    nodes: [
      { id: 'VoiceTurn', label: 'Voice turn', detail: 'User gives feedback aloud.', tone: 'voice' },
      {
        id: 'AgentEdit',
        label: 'Agent edit',
        detail: 'Agent replaces the diagram revision.',
        tone: 'agent',
      },
      {
        id: 'LiveArtifact',
        label: 'Live Diagram Artifact',
        detail: 'Rendered and source views stay paired.',
        tone: 'artifact',
      },
      {
        id: 'Approval',
        label: 'Approval checkpoint',
        detail: 'User confirms before repo changes.',
        tone: 'agent',
      },
      {
        id: 'RepoMutation',
        label: 'Repo mutation',
        detail: 'Only after explicit approval.',
        tone: 'artifact',
      },
    ],
    edges: [
      ['VoiceTurn', 'AgentEdit'],
      ['AgentEdit', 'LiveArtifact'],
      ['LiveArtifact', 'Approval'],
      ['Approval', 'RepoMutation'],
    ],
  },
];

const TRANSCRIPT = [
  {
    speaker: 'William',
    text: 'Can the agent change the diagram while I am talking through the workflow?',
  },
  {
    speaker: 'RepoLine',
    text: 'Yes. I will keep one live diagram artifact updated in the browser companion.',
  },
  {
    speaker: 'William',
    text: 'Make sure the source is visible too, so I can see exactly what changed.',
  },
];

function normalizeVariant(value: string | null): VariantKey {
  return value === 'B' || value === 'C' ? value : 'A';
}

function usePrototypeVariant() {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const current = normalizeVariant(searchParams.get('variant'));

  const setVariant = useCallback(
    (variant: VariantKey) => {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set('variant', variant);
      router.replace(`${pathname}?${nextParams.toString()}`, { scroll: false });
    },
    [pathname, router, searchParams]
  );

  return { current, setVariant };
}

function toneClass(tone: DiagramRevision['nodes'][number]['tone']) {
  if (tone === 'voice') {
    return 'border-cyan-300/30 bg-cyan-400/10 text-cyan-50';
  }

  if (tone === 'agent') {
    return 'border-amber-300/30 bg-amber-400/10 text-amber-50';
  }

  return 'border-emerald-300/30 bg-emerald-400/10 text-emerald-50';
}

function DiagramCanvas({
  revision,
  compact = false,
}: {
  revision: DiagramRevision;
  compact?: boolean;
}) {
  return (
    <div className='relative overflow-hidden rounded-lg border border-white/10 bg-[#071111] p-4'>
      <div className='pointer-events-none absolute inset-0 bg-[linear-gradient(rgba(255,255,255,.04)_1px,transparent_1px),linear-gradient(90deg,rgba(255,255,255,.04)_1px,transparent_1px)] bg-[size:28px_28px]' />
      <div
        className={cn(
          'relative grid gap-3',
          compact ? 'grid-cols-1' : 'grid-cols-2 xl:grid-cols-3'
        )}
      >
        {revision.nodes.map((node, index) => (
          <div
            className={cn('rounded-lg border p-3 shadow-xl shadow-black/20', toneClass(node.tone))}
            key={node.id}
          >
            <div className='flex items-center justify-between gap-2'>
              <span className='font-semibold text-sm'>{node.label}</span>
              <span className='rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-white/55'>
                {index + 1}
              </span>
            </div>
            <p className='mt-2 text-xs text-white/65 leading-relaxed'>{node.detail}</p>
          </div>
        ))}
      </div>
      <div className='relative mt-4 flex flex-wrap gap-2 text-[11px] text-white/45'>
        {revision.edges.map(([from, to]) => (
          <span
            className='rounded-full border border-white/10 bg-white/5 px-2 py-1'
            key={`${from}-${to}`}
          >
            {from} -&gt; {to}
          </span>
        ))}
      </div>
    </div>
  );
}

function SourcePanel({ revision }: { revision: DiagramRevision }) {
  return (
    <div className='rounded-lg border border-white/10 bg-black/45'>
      <div className='flex items-center justify-between border-white/10 border-b px-3 py-2'>
        <span className='font-medium text-white text-xs'>Mermaid source</span>
        <span className='rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-white/45'>
          {revision.source.split('\n').length} lines
        </span>
      </div>
      <pre className='max-h-72 overflow-auto p-3 font-mono text-[12px] text-emerald-100 leading-5'>
        {revision.source}
      </pre>
    </div>
  );
}

function StateInspector({
  revisionIndex,
  variant,
  mode,
}: {
  revisionIndex: number;
  variant: VariantKey;
  mode: string;
}) {
  const state = {
    question: 'Should Live Diagram Artifact feel ready as a browser companion experience?',
    variant,
    mode,
    artifactId: 'voice-session-diagram',
    artifactKind: 'diagram',
    language: 'mermaid',
    updatePolicy: 'replace latest stable artifact card',
    revision: REVISIONS[revisionIndex].id,
    revisionCount: revisionIndex + 1,
    productionReady: false,
  };

  return (
    <div className='rounded-lg border border-white/10 bg-black/35 p-3'>
      <div className='mb-2 flex items-center gap-2 text-white/70 text-xs'>
        <Code2Icon className='size-3.5' />
        Full prototype state
      </div>
      <pre className='overflow-auto whitespace-pre-wrap font-mono text-[11px] text-white/55 leading-5'>
        {JSON.stringify(state, null, 2)}
      </pre>
    </div>
  );
}

function PrototypeControls({
  revisionIndex,
  setRevisionIndex,
}: {
  revisionIndex: number;
  setRevisionIndex: (value: number) => void;
}) {
  const atEnd = revisionIndex === REVISIONS.length - 1;

  return (
    <div className='flex flex-wrap items-center gap-2'>
      <Button
        className='rounded-lg'
        onClick={() => setRevisionIndex(Math.min(REVISIONS.length - 1, revisionIndex + 1))}
        disabled={atEnd}
      >
        <SparklesIcon />
        Apply agent revision
      </Button>
      <Button className='rounded-lg' onClick={() => setRevisionIndex(0)} variant='outline'>
        <RotateCcwIcon />
        Reset
      </Button>
      <span className='text-white/45 text-xs'>
        Revision {revisionIndex + 1} of {REVISIONS.length}
      </span>
    </div>
  );
}

function VariantA({
  revision,
  revisionIndex,
  setRevisionIndex,
  variant,
}: {
  revision: DiagramRevision;
  revisionIndex: number;
  setRevisionIndex: (value: number) => void;
  variant: VariantKey;
}) {
  return (
    <main className='min-h-svh bg-[#080c0f] px-5 pt-24 pb-28 text-white md:px-8'>
      <section className='mx-auto grid max-w-6xl gap-5 lg:grid-cols-[minmax(0,0.78fr)_minmax(420px,1fr)]'>
        <div>
          <PrototypeHeader
            eyebrow='Variant A'
            title='Transcript card'
            description='The diagram lives where artifacts already appear: inside the conversation timeline as one persistent card.'
          />
          <div className='mt-5 space-y-3'>
            {TRANSCRIPT.map((turn) => (
              <div className='rounded-lg border border-white/10 bg-white/5 p-4' key={turn.text}>
                <div className='mb-1 font-medium text-white/80 text-xs'>{turn.speaker}</div>
                <p className='text-sm text-white/65 leading-relaxed'>{turn.text}</p>
              </div>
            ))}
          </div>
        </div>

        <div className='space-y-4'>
          <section className='rounded-lg border border-emerald-300/20 bg-emerald-400/10 p-4'>
            <div className='mb-4 flex items-start justify-between gap-3'>
              <div>
                <div className='font-semibold text-emerald-50'>{revision.title}</div>
                <p className='mt-1 text-emerald-100/65 text-sm'>{revision.agentNote}</p>
              </div>
              <span className='rounded-full border border-emerald-200/20 px-2 py-1 text-[10px] text-emerald-100/70 uppercase tracking-[0.16em]'>
                Live
              </span>
            </div>
            <DiagramCanvas revision={revision} compact={revision.nodes.length > 4} />
          </section>
          <SourcePanel revision={revision} />
          <PrototypeControls revisionIndex={revisionIndex} setRevisionIndex={setRevisionIndex} />
          <StateInspector
            mode='timeline artifact card'
            revisionIndex={revisionIndex}
            variant={variant}
          />
        </div>
      </section>
    </main>
  );
}

function VariantB({
  revision,
  revisionIndex,
  setRevisionIndex,
  variant,
}: {
  revision: DiagramRevision;
  revisionIndex: number;
  setRevisionIndex: (value: number) => void;
  variant: VariantKey;
}) {
  return (
    <main className='min-h-svh bg-[#10100d] px-5 pt-24 pb-28 text-white md:px-8'>
      <section className='mx-auto max-w-7xl'>
        <PrototypeHeader
          eyebrow='Variant B'
          title='Split studio'
          description='Conversation, rendered diagram, and source each get a stable pane so the user can compare what was said, what changed, and what the agent wrote.'
        />
        <div className='mt-6 grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)_380px]'>
          <aside className='rounded-lg border border-white/10 bg-white/5 p-4'>
            <div className='mb-4 flex items-center gap-2 font-semibold text-sm'>
              <MessageSquareTextIcon className='size-4 text-cyan-200' />
              Voice context
            </div>
            <div className='space-y-3'>
              {TRANSCRIPT.map((turn) => (
                <div className='rounded-lg bg-black/20 p-3' key={turn.text}>
                  <div className='text-white/55 text-xs'>{turn.speaker}</div>
                  <p className='mt-1 text-white/70 text-sm leading-relaxed'>{turn.text}</p>
                </div>
              ))}
            </div>
          </aside>

          <section className='rounded-lg border border-white/10 bg-white/5 p-4'>
            <div className='mb-4 flex flex-wrap items-center justify-between gap-3'>
              <div>
                <div className='font-semibold'>{revision.title}</div>
                <p className='text-white/55 text-sm'>{revision.agentNote}</p>
              </div>
              <PrototypeControls
                revisionIndex={revisionIndex}
                setRevisionIndex={setRevisionIndex}
              />
            </div>
            <DiagramCanvas revision={revision} />
          </section>

          <aside className='space-y-4'>
            <SourcePanel revision={revision} />
            <StateInspector
              mode='three-pane comparison'
              revisionIndex={revisionIndex}
              variant={variant}
            />
          </aside>
        </div>
      </section>
    </main>
  );
}

function VariantC({
  revision,
  revisionIndex,
  setRevisionIndex,
  variant,
}: {
  revision: DiagramRevision;
  revisionIndex: number;
  setRevisionIndex: (value: number) => void;
  variant: VariantKey;
}) {
  return (
    <main className='min-h-svh bg-[#09110f] px-5 pt-24 pb-28 text-white md:px-8'>
      <section className='mx-auto max-w-7xl'>
        <PrototypeHeader
          eyebrow='Variant C'
          title='Review board'
          description='The diagram is the main canvas, with revision history and approval boundary made explicit around it.'
        />
        <div className='mt-6 grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]'>
          <aside className='space-y-3'>
            {REVISIONS.map((candidate, index) => (
              <button
                className={cn(
                  'w-full rounded-lg border p-3 text-left transition-colors',
                  index === revisionIndex
                    ? 'border-emerald-300/40 bg-emerald-400/10'
                    : 'border-white/10 bg-white/5 hover:bg-white/10'
                )}
                key={candidate.id}
                onClick={() => setRevisionIndex(index)}
                type='button'
              >
                <div className='flex items-center justify-between gap-3'>
                  <span className='font-medium text-sm'>{candidate.title}</span>
                  {index <= revisionIndex && (
                    <CheckCircle2Icon className='size-4 text-emerald-200' />
                  )}
                </div>
                <p className='mt-1 text-white/50 text-xs leading-relaxed'>{candidate.agentNote}</p>
              </button>
            ))}
          </aside>

          <section className='space-y-4'>
            <div className='rounded-lg border border-white/10 bg-white/5 p-4'>
              <div className='mb-4 flex flex-wrap items-center justify-between gap-3'>
                <div className='flex items-center gap-2 text-sm text-white/60'>
                  <Maximize2Icon className='size-4 text-emerald-200' />
                  Persistent artifact id:{' '}
                  <span className='font-mono text-white'>voice-session-diagram</span>
                </div>
                <PrototypeControls
                  revisionIndex={revisionIndex}
                  setRevisionIndex={setRevisionIndex}
                />
              </div>
              <DiagramCanvas revision={revision} />
            </div>

            <div className='grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]'>
              <SourcePanel revision={revision} />
              <div className='space-y-4'>
                <div className='rounded-lg border border-amber-300/20 bg-amber-400/10 p-4'>
                  <div className='flex items-center gap-2 font-semibold text-amber-100 text-sm'>
                    <PanelRightIcon className='size-4' />
                    Approval boundary
                  </div>
                  <p className='mt-2 text-amber-50/70 text-sm leading-relaxed'>
                    Diagram revisions are safe visual artifacts. Any repo mutation stays behind a
                    separate approval checkpoint.
                  </p>
                </div>
                <StateInspector
                  mode='review board with revision rail'
                  revisionIndex={revisionIndex}
                  variant={variant}
                />
              </div>
            </div>
          </section>
        </div>
      </section>
    </main>
  );
}

function PrototypeHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description: string;
}) {
  return (
    <header>
      <div className='mb-3 inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-white/55 text-xs uppercase tracking-[0.18em]'>
        <BotIcon className='size-3.5' />
        {eyebrow}
      </div>
      <h1 className='max-w-4xl font-semibold text-4xl tracking-tight md:text-6xl'>{title}</h1>
      <p className='mt-4 max-w-3xl text-lg text-white/60 leading-relaxed'>{description}</p>
      <div className='mt-4 flex flex-wrap gap-2 text-xs text-white/50'>
        <span className='rounded-full border border-white/10 px-3 py-1'>PROTOTYPE - throwaway</span>
        <span className='rounded-full border border-white/10 px-3 py-1'>Live Diagram Artifact</span>
        <span className='rounded-full border border-white/10 px-3 py-1'>Mermaid-first</span>
        <span className='rounded-full border border-white/10 px-3 py-1'>No persistence</span>
      </div>
    </header>
  );
}

function PrototypeSwitcher({
  current,
  setVariant,
}: {
  current: VariantKey;
  setVariant: (variant: VariantKey) => void;
}) {
  const currentIndex = VARIANTS.findIndex((variant) => variant.key === current);
  const active = VARIANTS[currentIndex] ?? VARIANTS[0];
  const previous = VARIANTS[(currentIndex + VARIANTS.length - 1) % VARIANTS.length].key;
  const next = VARIANTS[(currentIndex + 1) % VARIANTS.length].key;

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (
        target?.tagName === 'INPUT' ||
        target?.tagName === 'TEXTAREA' ||
        target?.isContentEditable
      ) {
        return;
      }

      if (event.key === 'ArrowLeft') {
        event.preventDefault();
        setVariant(previous);
      }

      if (event.key === 'ArrowRight') {
        event.preventDefault();
        setVariant(next);
      }
    }

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [next, previous, setVariant]);

  if (process.env.NODE_ENV === 'production') {
    return null;
  }

  return (
    <div className='fixed bottom-4 left-1/2 z-[80] flex -translate-x-1/2 items-center gap-2 rounded-full border border-white/15 bg-black/80 p-2 text-white shadow-2xl shadow-black/40 backdrop-blur'>
      <Button
        aria-label='Previous variant'
        onClick={() => setVariant(previous)}
        size='icon-sm'
        variant='ghost'
      >
        <ArrowLeftIcon />
      </Button>
      <div className='min-w-52 px-2 text-center text-sm'>
        <span className='font-mono text-white/50'>{active.key}</span>
        <span className='mx-2 text-white/30'>-</span>
        <span className='font-medium'>{active.name}</span>
      </div>
      <Button
        aria-label='Next variant'
        onClick={() => setVariant(next)}
        size='icon-sm'
        variant='ghost'
      >
        <ArrowRightIcon />
      </Button>
    </div>
  );
}

export function LiveDiagramPrototype() {
  const { current, setVariant } = usePrototypeVariant();
  const [revisionIndex, setRevisionIndex] = useState(1);
  const revision = REVISIONS[revisionIndex];
  const renderedVariant = useMemo(() => {
    const props = { revision, revisionIndex, setRevisionIndex, variant: current };

    if (current === 'B') {
      return <VariantB {...props} />;
    }

    if (current === 'C') {
      return <VariantC {...props} />;
    }

    return <VariantA {...props} />;
  }, [current, revision, revisionIndex]);

  return (
    <>
      {renderedVariant}
      <PrototypeSwitcher current={current} setVariant={setVariant} />
      <div className='fixed top-4 right-4 z-[70] hidden items-center gap-2 rounded-full border border-emerald-300/20 bg-emerald-400/10 px-3 py-2 text-emerald-50 text-xs shadow-xl shadow-black/25 backdrop-blur md:flex'>
        <Clock3Icon className='size-3.5' />
        In-memory prototype
      </div>
    </>
  );
}
