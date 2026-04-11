import { expect, test } from 'bun:test';
import { mkdtempSync, mkdirSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

import {
  checkEnvKey,
  checkInstalledRepoLineSkill,
  checkPhoneState,
  commandInstallHint,
  isRepoLineCursorRule,
  isRepoLineSkillDirectory,
  projectSkillPath,
} from './bridge-doctor';
import type { SetupState } from './bridge-runtime-config';

test('checkEnvKey reports set and missing values', () => {
  expect(checkEnvKey('Agent env', { FOO: 'bar' }, 'FOO')).toEqual({
    name: 'Agent env FOO',
    ok: true,
    detail: 'set',
  });
  expect(checkEnvKey('Agent env', {}, 'FOO')).toEqual({
    name: 'Agent env FOO',
    ok: false,
    detail: 'missing',
  });
});

test('commandInstallHint maps supported setup tools', () => {
  expect(commandInstallHint('lk')).toBe('run `./scripts/bootstrap.sh lk`');
  expect(commandInstallHint('uv')).toBe('run `./scripts/bootstrap.sh uv`');
  expect(commandInstallHint('cursor-agent')).toBe('run `./scripts/bootstrap.sh cursor`');
  expect(commandInstallHint('unknown-tool')).toBeNull();
});

test('projectSkillPath maps providers to their install roots', () => {
  expect(projectSkillPath('claude')).toEqual(['.claude', 'skills']);
  expect(projectSkillPath('codex')).toEqual(['.agents', 'skills']);
  expect(projectSkillPath('cursor')).toEqual(['.cursor', 'rules']);
});

test('checkInstalledRepoLineSkill validates cursor rules', () => {
  const dir = mkdtempSync(join(tmpdir(), 'bridge-doctor-cursor-'));
  const targetPath = join(dir, '.cursor', 'rules', 'repoline-voice-session.mdc');
  mkdirSync(join(dir, '.cursor', 'rules'), { recursive: true });
  writeFileSync(
    targetPath,
    `---
description: RepoLine voice session behavior
alwaysApply: true
---

# RepoLine Voice Session
`
  );

  expect(isRepoLineCursorRule(targetPath, 'repoline-voice-session')).toBe(true);
  expect(
    checkInstalledRepoLineSkill('cursor', dir, 'repoline-voice-session')
  ).toEqual({
    name: 'RepoLine instructions install',
    ok: true,
    detail: targetPath,
  });
});

test('checkInstalledRepoLineSkill recognizes skill symlinks', () => {
  const dir = mkdtempSync(join(tmpdir(), 'bridge-doctor-symlink-'));
  const source = join(dir, 'source-skill');
  const target = join(dir, '.agents', 'skills', 'repoline-voice-session');
  mkdirSync(source, { recursive: true });
  mkdirSync(join(dir, '.agents', 'skills'), { recursive: true });
  writeFileSync(
    join(source, 'SKILL.md'),
    `---
name: repoline-voice-session
description: Example
---
`
  );
  symlinkSync(source, target, 'dir');

  expect(isRepoLineSkillDirectory(target, 'repoline-voice-session')).toBe(true);
  expect(
    checkInstalledRepoLineSkill('codex', dir, 'repoline-voice-session').detail
  ).toContain('(symlink)');
});

test('checkInstalledRepoLineSkill reports missing configuration clearly', () => {
  expect(checkInstalledRepoLineSkill('cursor', '/tmp/project', '')).toEqual({
    name: 'RepoLine instructions install',
    ok: false,
    detail: 'missing skill name',
  });
  expect(checkInstalledRepoLineSkill(null, '/tmp/project', 'repoline-voice-session')).toEqual({
    name: 'RepoLine instructions install',
    ok: false,
    detail: 'missing bridge provider',
  });
});

test('checkPhoneState validates dispatch coverage', () => {
  const state: SetupState = {
    configured_at: '2026-04-11T00:00:00.000Z',
    livekit_project_name: 'demo',
    livekit_url: 'wss://example.livekit.cloud',
    agent_name: 'clawdbot-agent',
    bridge_provider: 'cursor',
    workdir: '/tmp/project',
    phone: {
      number: '+15551234567',
      pin: '1234',
      dispatchRuleName: 'demo-rule',
      dispatchRuleId: 'rule_123',
    },
  };

  expect(
    checkPhoneState(
      state,
      () => ({
        sipDispatchRuleId: 'rule_123',
        trunkIds: ['PN_123'],
      }),
      () => 'PN_123'
    )
  ).toEqual({
    name: 'Phone number wiring',
    ok: true,
    detail: '+15551234567',
  });

  expect(
    checkPhoneState(
      state,
      () => ({
        sipDispatchRuleId: 'rule_123',
        trunkIds: ['PN_999'],
      }),
      () => 'PN_123'
    )
  ).toEqual({
    name: 'Phone number wiring',
    ok: false,
    detail: 'dispatch rule is not associated with the configured project number',
  });
});
