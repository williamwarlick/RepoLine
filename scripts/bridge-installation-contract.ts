import {
  cpSync,
  existsSync,
  mkdirSync,
  readFileSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import { join } from 'node:path';

import {
  REPOLINE_SKILL_NAME,
  REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
  buildAgentEnvValues,
  buildFrontendEnvValues,
  saveSetupState,
  type BridgeProvider,
  type PhoneConfig,
  type SetupState,
  writeEnvFile,
} from './bridge-runtime-config';
import {
  checkEnvKey,
  checkFileExists,
  checkInstalledRepoLineSkill,
  isRepoLineCursorRule,
  isRepoLineSkillDirectory,
  projectSkillPath,
  type DoctorCheck,
} from './bridge-doctor';

export type SkillInstallMethod = 'existing' | 'symlink' | 'copy' | 'generated';

export type SkillInstallationRecord = {
  method: SkillInstallMethod;
  targetPath: string;
};

export type BridgeInstallationSourcePaths = {
  skillSourceDir: string;
  skillSourcePath: string;
  cursorRuleSourcePath: string;
  ttsPronunciationSkillSourceDir: string;
  ttsPronunciationSkillSourcePath: string;
  ttsPronunciationNotesSourcePath: string;
};

export type BridgeRuntimeManifest = {
  agentEnv: Record<string, string>;
  frontendEnv: Record<string, string>;
  state: SetupState;
  pythonParity: {
    provider: BridgeProvider;
    workdir: string;
    skillName: string;
    ttsPronunciationSkillName: string;
  };
};

type RuntimeConfigOptions = {
  project: { name: string; url: string; apiKey: string; apiSecret: string };
  agentName: string;
  existingAgentEnv: Record<string, string>;
  existingFrontendEnv: Record<string, string>;
  phone: PhoneConfig | null;
  configuredAt?: string;
};

type PersistRuntimeConfigOptions = RuntimeConfigOptions & {
  agentEnvPath: string;
  frontendEnvPath: string;
  statePath: string;
};

type BridgeInstallationContractOptions = {
  repoRoot: string;
  provider: BridgeProvider | null;
  workdir: string;
  skillName?: string;
  ttsPronunciationSkillName?: string;
};

type MaterializeOptions = {
  ttsModel: string;
  ttsVoice: string;
};

export function createBridgeInstallationContract(
  options: BridgeInstallationContractOptions
) {
  const skillName = options.skillName ?? REPOLINE_SKILL_NAME;
  const ttsPronunciationSkillName =
    options.ttsPronunciationSkillName ?? REPOLINE_TTS_PRONUNCIATION_SKILL_NAME;
  const sourcePaths = resolveBridgeInstallationSourcePaths(
    options.repoRoot,
    skillName,
    ttsPronunciationSkillName
  );

  function sourceChecks(): DoctorCheck[] {
    return [
      checkFileExists('RepoLine voice skill source', sourcePaths.skillSourcePath),
      checkFileExists('RepoLine Cursor rule source', sourcePaths.cursorRuleSourcePath),
      checkFileExists(
        'RepoLine TTS pronunciation skill source',
        sourcePaths.ttsPronunciationSkillSourcePath
      ),
      checkFileExists(
        'RepoLine TTS pronunciation notes source',
        sourcePaths.ttsPronunciationNotesSourcePath
      ),
    ];
  }

  function renderRuntimeConfig(runtime: RuntimeConfigOptions): BridgeRuntimeManifest {
    const provider = requireProvider(options.provider);
    const configuredAt = runtime.configuredAt ?? new Date().toISOString();
    const state: SetupState = {
      configured_at: configuredAt,
      livekit_project_name: runtime.project.name,
      livekit_url: runtime.project.url,
      agent_name: runtime.agentName,
      bridge_provider: provider,
      workdir: options.workdir,
      phone: runtime.phone,
    };

    return {
      agentEnv: buildAgentEnvValues({
        project: runtime.project,
        agentName: runtime.agentName,
        bridgeProvider: provider,
        workdir: options.workdir,
        existingAgentEnv: runtime.existingAgentEnv,
      }),
      frontendEnv: buildFrontendEnvValues({
        project: runtime.project,
        agentName: runtime.agentName,
        existingFrontendEnv: runtime.existingFrontendEnv,
      }),
      state,
      pythonParity: {
        provider,
        workdir: options.workdir,
        skillName,
        ttsPronunciationSkillName,
      },
    };
  }

  function persistRuntimeConfig(runtime: PersistRuntimeConfigOptions): BridgeRuntimeManifest {
    const manifest = renderRuntimeConfig(runtime);
    writeEnvFile(runtime.agentEnvPath, manifest.agentEnv);
    writeEnvFile(runtime.frontendEnvPath, manifest.frontendEnv);
    saveSetupState(runtime.statePath, manifest.state);
    return manifest;
  }

  function materialize(install: MaterializeOptions): {
    instructions: SkillInstallationRecord;
    pronunciation: SkillInstallationRecord;
  } {
    const provider = requireProvider(options.provider);
    const workdir = requireWorkdir(options.workdir);

    return {
      instructions: installRepoLineSkill({
        provider,
        workdir,
        skillName,
        sourcePaths,
      }),
      pronunciation: installRepoLineTtsPronunciationSkill({
        provider,
        workdir,
        skillName: ttsPronunciationSkillName,
        sourcePaths,
        ttsModel: install.ttsModel,
        ttsVoice: install.ttsVoice,
      }),
    };
  }

  function doctor(args: {
    agentEnv: Record<string, string>;
    frontendEnv: Record<string, string>;
  }): DoctorCheck[] {
    const checks: DoctorCheck[] = [];
    for (const key of ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'LIVEKIT_AGENT_NAME']) {
      checks.push(checkEnvKey('Agent env', args.agentEnv, key));
    }
    for (const key of ['BRIDGE_CLI_PROVIDER', 'BRIDGE_WORKDIR', 'REPOLINE_SKILL_NAME']) {
      checks.push(checkEnvKey('Agent env', args.agentEnv, key));
    }
    checks.push(checkEnvKey('Agent env', args.agentEnv, 'REPOLINE_TTS_PRONUNCIATION_SKILL_NAME'));

    for (const key of ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'AGENT_NAME']) {
      checks.push(checkEnvKey('Frontend env', args.frontendEnv, key));
    }

    checks.push(
      checkInstalledRepoLineSkill(
        options.provider,
        options.workdir,
        skillName,
        'RepoLine instructions install'
      )
    );
    checks.push(
      checkInstalledRepoLineSkill(
        options.provider,
        options.workdir,
        ttsPronunciationSkillName,
        'RepoLine TTS pronunciation install'
      )
    );
    return checks;
  }

  function toPythonParityManifest() {
    return {
      provider: requireProvider(options.provider),
      workdir: requireWorkdir(options.workdir),
      skillName,
      ttsPronunciationSkillName,
    };
  }

  return {
    sourcePaths,
    sourceChecks,
    renderRuntimeConfig,
    persistRuntimeConfig,
    materialize,
    doctor,
    toPythonParityManifest,
  };
}

export function resolveBridgeInstallationSourcePaths(
  repoRoot: string,
  skillName = REPOLINE_SKILL_NAME,
  ttsPronunciationSkillName = REPOLINE_TTS_PRONUNCIATION_SKILL_NAME
): BridgeInstallationSourcePaths {
  const skillSourceDir = join(repoRoot, 'skills', skillName);
  const ttsPronunciationSkillSourceDir = join(repoRoot, 'skills', ttsPronunciationSkillName);

  return {
    skillSourceDir,
    skillSourcePath: join(skillSourceDir, 'SKILL.md'),
    cursorRuleSourcePath: join(skillSourceDir, 'cursor-rule.mdc'),
    ttsPronunciationSkillSourceDir,
    ttsPronunciationSkillSourcePath: join(ttsPronunciationSkillSourceDir, 'SKILL.md'),
    ttsPronunciationNotesSourcePath: join(
      ttsPronunciationSkillSourceDir,
      'references',
      'PROVIDER_NOTES.md'
    ),
  };
}

function installRepoLineSkill(options: {
  provider: BridgeProvider;
  workdir: string;
  skillName: string;
  sourcePaths: BridgeInstallationSourcePaths;
}): SkillInstallationRecord {
  if (!existsSync(options.sourcePaths.skillSourcePath)) {
    throw new Error(`RepoLine skill source not found: ${options.sourcePaths.skillSourcePath}`);
  }

  if (options.provider === 'cursor') {
    if (!existsSync(options.sourcePaths.cursorRuleSourcePath)) {
      throw new Error(
        `RepoLine Cursor rule source not found: ${options.sourcePaths.cursorRuleSourcePath}`
      );
    }

    const targetRoot = join(options.workdir, ...projectSkillPath(options.provider));
    const targetPath = join(targetRoot, `${options.skillName}.mdc`);
    mkdirSync(targetRoot, { recursive: true });

    if (existsSync(targetPath)) {
      if (!isRepoLineCursorRule(targetPath, options.skillName)) {
        throw new Error(`existing path is not a RepoLine rule install: ${targetPath}`);
      }
      return { method: 'existing', targetPath };
    }

    writeFileSync(targetPath, readFileSync(options.sourcePaths.cursorRuleSourcePath, 'utf8'));
    return { method: 'generated', targetPath };
  }

  const targetRoot = join(options.workdir, ...projectSkillPath(options.provider));
  const targetPath = join(targetRoot, options.skillName);
  mkdirSync(targetRoot, { recursive: true });

  if (existsSync(targetPath)) {
    if (!isRepoLineSkillDirectory(targetPath, options.skillName)) {
      throw new Error(`existing path is not a RepoLine skill install: ${targetPath}`);
    }
    return { method: 'existing', targetPath };
  }

  try {
    symlinkSync(options.sourcePaths.skillSourceDir, targetPath, 'dir');
    return { method: 'symlink', targetPath };
  } catch {
    cpSync(options.sourcePaths.skillSourceDir, targetPath, { recursive: true });
    return { method: 'copy', targetPath };
  }
}

function installRepoLineTtsPronunciationSkill(options: {
  provider: BridgeProvider;
  workdir: string;
  skillName: string;
  sourcePaths: BridgeInstallationSourcePaths;
  ttsModel: string;
  ttsVoice: string;
}): SkillInstallationRecord {
  if (!existsSync(options.sourcePaths.ttsPronunciationSkillSourcePath)) {
    throw new Error(
      `RepoLine TTS pronunciation skill source not found: ${options.sourcePaths.ttsPronunciationSkillSourcePath}`
    );
  }

  if (options.provider === 'cursor') {
    const targetRoot = join(options.workdir, ...projectSkillPath(options.provider));
    const targetPath = join(targetRoot, `${options.skillName}.mdc`);
    mkdirSync(targetRoot, { recursive: true });

    if (existsSync(targetPath)) {
      if (!isRepoLineCursorRule(targetPath, options.skillName)) {
        throw new Error(
          `existing path is not a RepoLine TTS pronunciation rule install: ${targetPath}`
        );
      }
      return { method: 'existing', targetPath };
    }

    writeFileSync(
      targetPath,
      buildRepoLineTtsPronunciationCursorRule(options.ttsModel, options.ttsVoice)
    );
    return { method: 'generated', targetPath };
  }

  const targetRoot = join(options.workdir, ...projectSkillPath(options.provider));
  const targetPath = join(targetRoot, options.skillName);
  mkdirSync(targetRoot, { recursive: true });

  if (existsSync(targetPath)) {
    if (!isRepoLineSkillDirectory(targetPath, options.skillName)) {
      throw new Error(
        `existing path is not a RepoLine TTS pronunciation skill install: ${targetPath}`
      );
    }
    ensureRepoLineTtsPronunciationNotes(targetPath, options.ttsModel, options.ttsVoice, false);
    return { method: 'existing', targetPath };
  }

  cpSync(options.sourcePaths.ttsPronunciationSkillSourceDir, targetPath, { recursive: true });
  ensureRepoLineTtsPronunciationNotes(targetPath, options.ttsModel, options.ttsVoice, true);
  return { method: 'generated', targetPath };
}

function ensureRepoLineTtsPronunciationNotes(
  skillPath: string,
  ttsModel: string,
  ttsVoice: string,
  overwrite: boolean
): void {
  const notesPath = join(skillPath, 'references', 'PROVIDER_NOTES.md');
  if (!overwrite && existsSync(notesPath)) {
    return;
  }

  writeFileSync(notesPath, buildRepoLineTtsPronunciationNotes(ttsModel, ttsVoice));
}

function buildRepoLineTtsPronunciationNotes(ttsModel: string, ttsVoice: string): string {
  return [
    '# Provider Notes',
    '',
    '## Current Provider',
    '',
    `- TTS model: ${ttsModel}`,
    `- TTS voice: ${ttsVoice}`,
    '',
    '## How To Update',
    '',
    '- Keep rules specific to this TTS model and voice.',
    '- Add short lines that say what to say or what to avoid.',
    '',
    '## Active Pronunciation Rules',
    '',
    '- Say `README.md` as "read me."',
    '- Do not spell out `README.md` letter by letter.',
    '',
  ].join('\n');
}

function buildRepoLineTtsPronunciationCursorRule(ttsModel: string, ttsVoice: string): string {
  return [
    '---',
    'description: RepoLine TTS pronunciation behavior',
    'alwaysApply: true',
    '---',
    '',
    '# RepoLine TTS Pronunciation',
    '',
    'Apply this rule in RepoLine voice sessions when the user corrects how something should sound.',
    '',
    '## Current Provider',
    '',
    `- TTS model: ${ttsModel}`,
    `- TTS voice: ${ttsVoice}`,
    '',
    '## What To Do',
    '',
    '- Treat "you said that weird" as actionable speech feedback.',
    '- Fix the wording immediately in the current reply when possible.',
    '- Update the pronunciation rules in this file so the correction sticks for this provider.',
    '- Keep every rule short, explicit, and easy to apply while speaking.',
    '',
    '## Active Pronunciation Rules',
    '',
    '- Say `README.md` as "read me."',
    '- Do not spell out `README.md` letter by letter.',
    '',
  ].join('\n');
}

function requireProvider(provider: BridgeProvider | null): BridgeProvider {
  if (!provider) {
    throw new Error('Bridge provider is required');
  }
  return provider;
}

function requireWorkdir(workdir: string): string {
  if (!workdir) {
    throw new Error('Bridge workdir is required');
  }
  return workdir;
}
