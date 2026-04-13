import { expect, test } from 'bun:test';
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

import {
  createBridgeInstallationContract,
  resolveBridgeInstallationSourcePaths,
} from './bridge-installation-contract';
import { REPOLINE_SKILL_NAME, REPOLINE_TTS_PRONUNCIATION_SKILL_NAME } from './bridge-runtime-config';

const REPO_ROOT = resolve(import.meta.dir, '..');

test('bridge installation contract renders runtime config and python parity metadata', () => {
  const contract = createBridgeInstallationContract({
    repoRoot: REPO_ROOT,
    provider: 'codex',
    workdir: '/tmp/project',
  });

  const manifest = contract.renderRuntimeConfig({
    project: {
      name: 'demo',
      url: 'wss://demo.livekit.cloud',
      apiKey: 'key',
      apiSecret: 'secret',
    },
    agentName: 'smoke-agent',
    existingAgentEnv: {},
    existingFrontendEnv: {},
    phone: null,
    configuredAt: '2026-04-13T12:00:00.000Z',
  });

  expect(manifest.state).toEqual({
    configured_at: '2026-04-13T12:00:00.000Z',
    livekit_project_name: 'demo',
    livekit_url: 'wss://demo.livekit.cloud',
    agent_name: 'smoke-agent',
    bridge_provider: 'codex',
    workdir: '/tmp/project',
    phone: null,
  });
  expect(manifest.agentEnv.BRIDGE_CLI_PROVIDER).toBe('codex');
  expect(manifest.frontendEnv.AGENT_NAME).toBe('smoke-agent');
  expect(manifest.pythonParity).toEqual({
    provider: 'codex',
    workdir: '/tmp/project',
    skillName: REPOLINE_SKILL_NAME,
    ttsPronunciationSkillName: REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
  });
});

test('bridge installation contract materializes cursor rules into the configured workdir', () => {
  const dir = mkdtempSync(join(tmpdir(), 'bridge-contract-'));

  try {
    const workdir = join(dir, 'repo');
    mkdirSync(workdir, { recursive: true });
    const contract = createBridgeInstallationContract({
      repoRoot: REPO_ROOT,
      provider: 'cursor',
      workdir,
    });

    const installed = contract.materialize({
      ttsModel: 'cartesia/sonic-3',
      ttsVoice: 'voice-123',
    });

    expect(installed.instructions.method).toBe('generated');
    expect(installed.pronunciation.method).toBe('generated');
    expect(existsSync(join(workdir, '.cursor', 'rules', `${REPOLINE_SKILL_NAME}.mdc`))).toBe(true);
    expect(
      readFileSync(
        join(workdir, '.cursor', 'rules', `${REPOLINE_TTS_PRONUNCIATION_SKILL_NAME}.mdc`),
        'utf8'
      )
    ).toContain('voice-123');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('bridge installation contract resolves skill source paths from the repo root', () => {
  const sourcePaths = resolveBridgeInstallationSourcePaths(REPO_ROOT);

  expect(sourcePaths.skillSourcePath).toBe(
    join(REPO_ROOT, 'skills', REPOLINE_SKILL_NAME, 'SKILL.md')
  );
  expect(sourcePaths.ttsPronunciationNotesSourcePath).toBe(
    join(
      REPO_ROOT,
      'skills',
      REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
      'references',
      'PROVIDER_NOTES.md'
    )
  );
});
