#!/usr/bin/env bun

import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  renameSync,
  symlinkSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { createInterface } from 'node:readline/promises';
import { fileURLToPath } from 'node:url';

type LiveKitProject = {
  name: string;
  url: string;
  apiKey: string;
  apiSecret: string;
  projectId: string | null;
};

type PhoneConfig = {
  number: string;
  pin: string;
  dispatchRuleName: string;
  dispatchRuleId: string;
};

type SetupState = {
  configured_at: string;
  livekit_project_name: string;
  livekit_url: string;
  agent_name: string;
  bridge_provider: string;
  claude_workdir: string;
  phone: PhoneConfig | null;
};

type RawState = {
  configured_at: string;
  livekit_project_name: string;
  livekit_url: string;
  agent_name: string;
  bridge_provider?: string;
  claude_workdir: string;
  phone?: {
    number: string;
    pin: string;
    dispatchRuleName?: string;
    dispatchRuleId?: string;
    dispatch_rule_name?: string;
    dispatch_rule_id?: string;
  } | null;
};

type PhoneNumberRecord = {
  e164Format: string;
  locality?: string;
  region?: string;
  status?: string;
};

type DispatchRuleRecord = {
  sipDispatchRuleId: string;
  name?: string;
  inboundNumbers?: string[];
};

const __filename = fileURLToPath(import.meta.url);
const REPO_ROOT = resolve(dirname(__filename), '..');
const AGENT_DIR = join(REPO_ROOT, 'agent');
const FRONTEND_DIR = join(REPO_ROOT, 'frontend');
const AGENT_ENV_PATH = join(AGENT_DIR, '.env.local');
const FRONTEND_ENV_PATH = join(FRONTEND_DIR, '.env.local');
const STATE_DIR = join(REPO_ROOT, '.bridge');
const STATE_PATH = join(STATE_DIR, 'state.json');
const PHONE_NUMBER_STATUS_ACTIVE = 'PHONE_NUMBER_STATUS_ACTIVE';
const REPOLINE_SKILL_NAME = 'repoline-voice-session';
const REPOLINE_SKILL_SOURCE_DIR = join(REPO_ROOT, 'skills', REPOLINE_SKILL_NAME);
const REPOLINE_SKILL_SOURCE_PATH = join(REPOLINE_SKILL_SOURCE_DIR, 'SKILL.md');

class BridgeCliError extends Error {}

const command = process.argv[2];

if (!command || !['setup', 'dev', 'doctor'].includes(command)) {
  printHelp();
  process.exit(command ? 1 : 0);
}

try {
  switch (command) {
    case 'setup':
      await setupCommand();
      break;
    case 'dev':
      await devCommand();
      break;
    case 'doctor':
      doctorCommand();
      break;
  }
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Error: ${message}`);
  process.exit(1);
}

function printHelp(): void {
  console.log(`Usage: bun run ${basename(__filename)} <setup|dev|doctor>`);
}

async function setupCommand(): Promise<void> {
  console.log('RepoLine setup');
  console.log(
    'This will write local env files, install dependencies, and optionally wire a project phone number.'
  );
  console.log();

  requireTools('lk', 'uv', 'bun');

  const agentEnv = loadEnvFile(AGENT_ENV_PATH);
  const frontendEnv = loadEnvFile(FRONTEND_ENV_PATH);
  const existingState = loadState();

  const ui = createPrompter();
  try {
    const bridgeProvider = await selectBridgeProvider(ui, agentEnv, existingState);
    requireTools(bridgeProvider);

    const project = await selectLiveKitProject(ui, agentEnv);
    const projectNumbers = listPhoneNumbers(project.name);
    const agentNameDefault =
      agentEnv.LIVEKIT_AGENT_NAME ??
      frontendEnv.AGENT_NAME ??
      existingState?.agent_name ??
      'clawdbot-agent';
    const agentName = await ui.promptText('LiveKit agent name', agentNameDefault);
    const claudeWorkdir = await selectWorkdir(
      ui,
      agentEnv.BRIDGE_WORKDIR ?? agentEnv.CLAUDE_WORKDIR ?? existingState?.claude_workdir ?? null
    );
    const skillInstall = installRepoLineSkill(bridgeProvider, claudeWorkdir);

    let phoneConfig: PhoneConfig | null = null;
    const shouldSetupPhone = await ui.promptBool(
      'Configure an inbound phone number now?',
      projectNumbers.length > 0 || existingState?.phone != null
    );
    if (shouldSetupPhone) {
      phoneConfig = await configurePhone(
        ui,
        project,
        agentName,
        existingState?.phone ?? null,
        projectNumbers
      );
    }

    writeEnvFiles({
      project,
      agentName,
      bridgeProvider,
      claudeWorkdir,
      existingAgentEnv: agentEnv,
      existingFrontendEnv: frontendEnv,
    });

    saveState({
      configured_at: new Date().toISOString(),
      livekit_project_name: project.name,
      livekit_url: project.url,
      agent_name: agentName,
      bridge_provider: bridgeProvider,
      claude_workdir: claudeWorkdir,
      phone: phoneConfig,
    });

    console.log();
    console.log('Installing dependencies and pre-downloading agent assets...');
    runChecked(['uv', 'sync'], {
      cwd: AGENT_DIR,
      envOverrides: { VIRTUAL_ENV: null },
    });
    runChecked(['uv', 'run', 'python', 'src/agent.py', 'download-files'], {
      cwd: AGENT_DIR,
      envOverrides: { VIRTUAL_ENV: null },
    });
    runChecked(['bun', 'install'], { cwd: FRONTEND_DIR });

    console.log();
    console.log('Setup complete.');
    console.log(`- LiveKit project: ${project.name}`);
    console.log(`- Coding CLI: ${formatBridgeProvider(bridgeProvider)}`);
    console.log(`- Workdir: ${claudeWorkdir}`);
    console.log(`- RepoLine skill: ${skillInstall.targetPath} (${skillInstall.method})`);
    console.log(`- Agent name: ${agentName}`);
    if (phoneConfig) {
      console.log(`- Call this number to chat: ${phoneConfig.number}`);
      console.log(`- Caller PIN: ${phoneConfig.pin}`);
      console.log(`- Dispatch rule: ${phoneConfig.dispatchRuleName}`);
    }
    console.log('- Next step: bun run dev');
  } finally {
    ui.close();
  }
}

async function devCommand(): Promise<void> {
  if (!existsSync(AGENT_ENV_PATH) || !existsSync(FRONTEND_ENV_PATH)) {
    throw new BridgeCliError('run `bun run setup` first.');
  }

  requireTools('uv', 'bun');

  const children = [
    spawnProcess(['uv', 'run', 'python', 'src/agent.py', 'dev'], {
      cwd: AGENT_DIR,
      envOverrides: { PYTHONUNBUFFERED: '1', VIRTUAL_ENV: null },
    }),
    spawnProcess(['bun', 'run', 'dev:network'], {
      cwd: FRONTEND_DIR,
    }),
  ];

  let settled = false;
  const terminateAll = (signal: NodeJS.Signals) => {
    for (const child of children) {
      if (child.exitCode === null) {
        child.kill(signal);
      }
    }
  };

  const cleanupAndExit = async (code: number) => {
    if (settled) {
      return;
    }
    settled = true;
    terminateAll('SIGTERM');
    await Bun.sleep(500);
    for (const child of children) {
      if (child.exitCode === null) {
        child.kill('SIGKILL');
      }
    }
    process.exit(code);
  };

  process.once('SIGINT', () => void cleanupAndExit(130));
  process.once('SIGTERM', () => void cleanupAndExit(143));

  await Promise.race(
    children.map(
      (child) =>
        new Promise<void>((resolve) => {
          child.once('exit', (code) => {
            void cleanupAndExit(code ?? 1);
            resolve();
          });
        })
    )
  );
}

function doctorCommand(): void {
  const checks: Array<{ name: string; ok: boolean; detail: string }> = [];

  checks.push(checkFileExists('Agent env', AGENT_ENV_PATH));
  checks.push(checkFileExists('Frontend env', FRONTEND_ENV_PATH));
  checks.push(checkFileExists('Frontend Bun lockfile', join(FRONTEND_DIR, 'bun.lock')));
  checks.push(checkFileExists('RepoLine voice skill source', REPOLINE_SKILL_SOURCE_PATH));

  const agentEnv = loadEnvFile(AGENT_ENV_PATH);
  const frontendEnv = loadEnvFile(FRONTEND_ENV_PATH);
  const state = loadState();
  const bridgeProvider = normalizeBridgeProvider(
    agentEnv.BRIDGE_CLI_PROVIDER ?? state?.bridge_provider ?? 'claude'
  );
  const workdir = agentEnv.BRIDGE_WORKDIR ?? agentEnv.CLAUDE_WORKDIR ?? state?.claude_workdir ?? '';
  const repolineSkillName = agentEnv.REPOLINE_SKILL_NAME ?? REPOLINE_SKILL_NAME;

  for (const tool of [bridgeProvider, 'lk', 'uv', 'bun']) {
    checks.push(checkCommandAvailable(tool));
  }

  for (const key of ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'LIVEKIT_AGENT_NAME']) {
    checks.push(checkEnvKey('Agent env', agentEnv, key));
  }
  checks.push(
    checkAnyEnvKey('Agent env bridge provider', agentEnv, ['BRIDGE_CLI_PROVIDER'], bridgeProvider)
  );
  checks.push(
    checkAnyEnvKey('Agent env bridge workdir', agentEnv, ['BRIDGE_WORKDIR', 'CLAUDE_WORKDIR'])
  );
  checks.push(
    checkAnyEnvKey('Agent env RepoLine skill', agentEnv, ['REPOLINE_SKILL_NAME'], repolineSkillName)
  );

  for (const key of ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'AGENT_NAME']) {
    checks.push(checkEnvKey('Frontend env', frontendEnv, key));
  }

  checks.push(runStatusCheck(`${formatBridgeProvider(bridgeProvider)} auth`, bridgeAuthCommand(bridgeProvider), REPO_ROOT));
  checks.push(
    runStatusCheck('Agent dependencies', ['uv', 'sync', '--check'], AGENT_DIR, {
      VIRTUAL_ENV: null,
    })
  );
  checks.push(runStatusCheck('Frontend dependencies', ['bun', 'install', '--frozen-lockfile'], FRONTEND_DIR));
  checks.push(checkInstalledRepoLineSkill(bridgeProvider, workdir, repolineSkillName));

  if (state) {
    checks.push(
      runStatusCheck(
        'LiveKit project link',
        ['lk', '--project', state.livekit_project_name, 'project', 'list', '-j'],
        REPO_ROOT
      )
    );
    if (state.phone) {
      checks.push(checkPhoneState(state));
    }
  }

  const width = Math.max(...checks.map((check) => check.name.length), 10);
  let failures = 0;
  for (const check of checks) {
    const marker = check.ok ? 'OK' : 'FAIL';
    if (!check.ok) {
      failures += 1;
    }
    console.log(`[${marker.padEnd(4)}] ${check.name.padEnd(width)} ${check.detail}`);
  }

  if (failures > 0) {
    throw new BridgeCliError('doctor found issues; fix the failed checks above.');
  }

  console.log('All checks passed.');
}

function spawnProcess(
  cmd: string[],
  options: {
    cwd: string;
    envOverrides?: Record<string, string | null>;
  }
): ChildProcess {
  return spawn(cmd[0], cmd.slice(1), {
    cwd: options.cwd,
    stdio: 'inherit',
    env: buildEnv(options.envOverrides),
  });
}

function selectDispatchRule(
  projectName: string,
  dispatchRuleName: string
): DispatchRuleRecord | null {
  const payload = runJsonCommand(['lk', '--project', projectName, 'sip', 'dispatch', 'list', '-j'], {
    cwd: REPO_ROOT,
  }) as { items?: DispatchRuleRecord[] };
  const items = payload.items ?? [];
  return items.find((item) => item.name === dispatchRuleName) ?? null;
}

async function selectLiveKitProject(
  ui: ReturnType<typeof createPrompter>,
  existingAgentEnv: Record<string, string>
): Promise<LiveKitProject> {
  const payload = runJsonCommand(['lk', 'project', 'list', '-j'], { cwd: REPO_ROOT });
  if (!Array.isArray(payload) || payload.length === 0) {
    throw new BridgeCliError('no LiveKit projects found. Run `lk project add` first.');
  }

  const projects = payload.map((item) => ({
    name: item.Name,
    url: item.URL,
    apiKey: item.APIKey,
    apiSecret: item.APISecret,
    projectId: item.ProjectId || null,
  })) as LiveKitProject[];

  let defaultIndex = 0;
  const currentUrl = existingAgentEnv.LIVEKIT_URL;
  if (currentUrl) {
    const matchingIndex = projects.findIndex((project) => project.url === currentUrl);
    if (matchingIndex >= 0) {
      defaultIndex = matchingIndex;
    }
  }

  const selection = await ui.selectOption(
    'Choose the linked LiveKit project',
    projects.map((project) => `${project.name} (${project.url})`),
    defaultIndex
  );
  return projects[selection];
}

async function selectWorkdir(
  ui: ReturnType<typeof createPrompter>,
  existingWorkdir: string | null
): Promise<string> {
  const candidates = discoverRepoCandidates(existingWorkdir);
  const options = candidates.map((candidate) => `${basename(candidate)} (${candidate})`);
  options.push('Enter a path manually');

  const selection = await ui.selectOption('Choose the coding CLI workdir', options, 0);
  if (selection === candidates.length) {
    while (true) {
      const value = await ui.promptText('Path to the repo', existingWorkdir ?? undefined);
      const resolved = resolveHome(value);
      if (isDirectory(resolved)) {
        return resolved;
      }
      console.log(`Path does not exist: ${resolved}`);
    }
  }

  return candidates[selection];
}

function discoverRepoCandidates(existingWorkdir: string | null): string[] {
  const seen = new Set<string>();
  const candidates: string[] = [];

  const addCandidate = (pathValue: string | null) => {
    if (!pathValue) {
      return;
    }
    const resolved = resolveHome(pathValue);
    if (!isDirectory(resolved) || !existsSync(join(resolved, '.git')) || seen.has(resolved)) {
      return;
    }
    seen.add(resolved);
    candidates.push(resolved);
  };

  addCandidate(existingWorkdir);
  addCandidate(REPO_ROOT);

  for (const parent of [dirname(REPO_ROOT), join(process.env.HOME ?? '', 'development')]) {
    if (!isDirectory(parent)) {
      continue;
    }
    for (const entry of readdirSync(parent, { withFileTypes: true })) {
      if (candidates.length >= 12) {
        break;
      }
      if (entry.isDirectory()) {
        addCandidate(join(parent, entry.name));
      }
    }
  }

  if (candidates.length === 0) {
    throw new BridgeCliError('no local git repos found; enter the target repo path manually.');
  }

  return candidates;
}

async function configurePhone(
  ui: ReturnType<typeof createPrompter>,
  project: LiveKitProject,
  agentName: string,
  existingPhone: PhoneConfig | null,
  projectNumbers: PhoneNumberRecord[]
): Promise<PhoneConfig> {
  const phoneNumber = await choosePhoneNumber(ui, projectNumbers, existingPhone?.number ?? null);
  const pin = await promptPin(ui, existingPhone?.pin ?? null);
  const dispatchRuleName = slugify(`${agentName}-inbound`);

  const dispatchPayload = {
    name: dispatchRuleName,
    rule: {
      dispatchRuleIndividual: {
        roomPrefix: 'call-',
        pin,
      },
    },
    roomConfig: {
      agents: [
        {
          agentName,
          metadata: JSON.stringify({
            agent: agentName,
            source: 'livekit-telephony',
          }),
        },
      ],
    },
    inboundNumbers: [phoneNumber],
  };

  const existingDispatch = selectDispatchRule(project.name, dispatchRuleName);
  if (existingDispatch) {
    runChecked(
      [
        'lk',
        '--project',
        project.name,
        'sip',
        'dispatch',
        'update',
        '--id',
        existingDispatch.sipDispatchRuleId,
        '-',
      ],
      {
        cwd: REPO_ROOT,
        stdinText: JSON.stringify(dispatchPayload),
      }
    );
  } else {
    runChecked(['lk', '--project', project.name, 'sip', 'dispatch', 'create', '-'], {
      cwd: REPO_ROOT,
      stdinText: JSON.stringify({ dispatch_rule: dispatchPayload }),
    });
  }

  const dispatch = selectDispatchRule(project.name, dispatchRuleName);
  if (!dispatch) {
    throw new BridgeCliError('failed to locate the SIP dispatch rule after creation.');
  }

  return {
    number: phoneNumber,
    pin,
    dispatchRuleName,
    dispatchRuleId: dispatch.sipDispatchRuleId,
  };
}

async function choosePhoneNumber(
  ui: ReturnType<typeof createPrompter>,
  numbers: PhoneNumberRecord[],
  existingNumber: string | null
): Promise<string> {
  if (numbers.length === 0) {
    throw new BridgeCliError(
      'no active phone number was found for this LiveKit project. Add one in LiveKit first, then rerun setup.'
    );
  }

  if (numbers.length === 1) {
    const phoneNumber = numbers[0].e164Format;
    console.log(`Using project phone number: ${phoneNumber}`);
    return phoneNumber;
  }

  let defaultIndex = 0;
  if (existingNumber) {
    const matchingIndex = numbers.findIndex((item) => item.e164Format === existingNumber);
    if (matchingIndex >= 0) {
      defaultIndex = matchingIndex;
    }
  }

  const selection = await ui.selectOption(
    'Choose the project phone number to attach',
    numbers.map((item) => formatPhoneNumberOption(item)),
    defaultIndex
  );
  return numbers[selection].e164Format;
}

function listPhoneNumbers(projectName: string): PhoneNumberRecord[] {
  const payload = runJsonCommand(['lk', '--project', projectName, 'number', 'list', '-j'], {
    cwd: REPO_ROOT,
  }) as { items?: PhoneNumberRecord[] };
  const items = payload.items ?? [];
  return items.filter(
    (item) => item.status === PHONE_NUMBER_STATUS_ACTIVE && typeof item.e164Format === 'string'
  );
}

async function promptPin(
  ui: ReturnType<typeof createPrompter>,
  defaultValue: string | null
): Promise<string> {
  while (true) {
    const value = await ui.promptText('Inbound caller PIN', defaultValue ?? undefined);
    if (/^\d{4}$/.test(value)) {
      return value;
    }
    console.log('PIN must be exactly 4 digits.');
  }
}

function writeEnvFiles(options: {
  project: LiveKitProject;
  agentName: string;
  bridgeProvider: string;
  claudeWorkdir: string;
  existingAgentEnv: Record<string, string>;
  existingFrontendEnv: Record<string, string>;
}): void {
  const agentEnv = {
    LIVEKIT_URL: options.project.url,
    LIVEKIT_API_KEY: options.project.apiKey,
    LIVEKIT_API_SECRET: options.project.apiSecret,
    LIVEKIT_AGENT_NAME: options.agentName,
    BRIDGE_CLI_PROVIDER: options.bridgeProvider,
    BRIDGE_WORKDIR: options.claudeWorkdir,
    BRIDGE_MODEL:
      options.existingAgentEnv.BRIDGE_MODEL ?? options.existingAgentEnv.CLAUDE_MODEL ?? '',
    REPOLINE_SKILL_NAME:
      options.existingAgentEnv.REPOLINE_SKILL_NAME ?? REPOLINE_SKILL_NAME,
    BRIDGE_SYSTEM_PROMPT:
      options.existingAgentEnv.BRIDGE_SYSTEM_PROMPT ??
      options.existingAgentEnv.CLAUDE_SYSTEM_PROMPT ??
      '',
    BRIDGE_CHUNK_CHARS:
      options.existingAgentEnv.BRIDGE_CHUNK_CHARS ??
      options.existingAgentEnv.CLAUDE_CHUNK_CHARS ??
      '140',
    CLAUDE_WORKDIR: options.claudeWorkdir,
    CLAUDE_MODEL:
      options.existingAgentEnv.CLAUDE_MODEL ?? options.existingAgentEnv.BRIDGE_MODEL ?? '',
    CLAUDE_SYSTEM_PROMPT:
      options.existingAgentEnv.CLAUDE_SYSTEM_PROMPT ??
      options.existingAgentEnv.BRIDGE_SYSTEM_PROMPT ??
      '',
    CLAUDE_CHUNK_CHARS:
      options.existingAgentEnv.CLAUDE_CHUNK_CHARS ??
      options.existingAgentEnv.BRIDGE_CHUNK_CHARS ??
      '140',
    CODEX_DANGEROUSLY_BYPASS_APPROVALS_AND_SANDBOX:
      options.existingAgentEnv.CODEX_DANGEROUSLY_BYPASS_APPROVALS_AND_SANDBOX ?? 'true',
    FINAL_TRANSCRIPT_DEBOUNCE_SECONDS:
      options.existingAgentEnv.FINAL_TRANSCRIPT_DEBOUNCE_SECONDS ?? '0.85',
    LIVEKIT_STT_MODEL: options.existingAgentEnv.LIVEKIT_STT_MODEL ?? 'deepgram/nova-3',
    LIVEKIT_STT_LANGUAGE: options.existingAgentEnv.LIVEKIT_STT_LANGUAGE ?? 'multi',
    LIVEKIT_TTS_MODEL: options.existingAgentEnv.LIVEKIT_TTS_MODEL ?? 'cartesia/sonic-3',
    LIVEKIT_TTS_VOICE:
      options.existingAgentEnv.LIVEKIT_TTS_VOICE ?? '9626c31c-bec5-4cca-baa8-f8ba9e84c8bc',
    BRIDGE_GREETING:
      options.existingAgentEnv.BRIDGE_GREETING ??
      'RepoLine is live. What do you want to work on?',
  };

  const frontendEnv = {
    LIVEKIT_API_KEY: options.project.apiKey,
    LIVEKIT_API_SECRET: options.project.apiSecret,
    LIVEKIT_URL: options.project.url,
    AGENT_NAME: options.agentName,
    NEXT_PUBLIC_APP_CONFIG_ENDPOINT:
      options.existingFrontendEnv.NEXT_PUBLIC_APP_CONFIG_ENDPOINT ?? '',
    SANDBOX_ID: options.existingFrontendEnv.SANDBOX_ID ?? '',
  };

  writeEnvFile(AGENT_ENV_PATH, agentEnv);
  writeEnvFile(FRONTEND_ENV_PATH, frontendEnv);
}

function writeEnvFile(pathValue: string, values: Record<string, string>): void {
  const lines = ['# Generated by `bun run setup`.', ''];
  for (const [key, value] of Object.entries(values)) {
    lines.push(`${key}=${formatEnvValue(value)}`);
  }
  const nextContents = `${lines.join('\n')}\n`;

  if (existsSync(pathValue)) {
    const currentContents = readFileSync(pathValue, 'utf8');
    if (currentContents === nextContents) {
      return;
    }
    renameSync(pathValue, `${pathValue}.bak`);
  }

  writeFileSync(pathValue, nextContents);
}

function formatEnvValue(value: string): string {
  if (value.length === 0) {
    return '';
  }
  if (/^[A-Za-z0-9_./:@+-]+$/.test(value)) {
    return value;
  }
  return `"${value.replaceAll('\\', '\\\\').replaceAll('"', '\\"')}"`;
}

function loadEnvFile(pathValue: string): Record<string, string> {
  if (!existsSync(pathValue)) {
    return {};
  }

  const env: Record<string, string> = {};
  const contents = readFileSync(pathValue, 'utf8');
  for (const line of contents.split(/\r?\n/)) {
    const stripped = line.trim();
    if (!stripped || stripped.startsWith('#') || !line.includes('=')) {
      continue;
    }
    const [key, ...rest] = line.split('=');
    let value = rest.join('=').trim();
    if (value.startsWith('"') && value.endsWith('"')) {
      value = value.slice(1, -1).replaceAll('\\"', '"').replaceAll('\\\\', '\\');
    }
    env[key.trim()] = value;
  }
  return env;
}

function saveState(state: SetupState): void {
  mkdirSync(STATE_DIR, { recursive: true });
  writeFileSync(STATE_PATH, `${JSON.stringify(state, null, 2)}\n`);
}

function loadState(): SetupState | null {
  if (!existsSync(STATE_PATH)) {
    return null;
  }
  const rawState = JSON.parse(readFileSync(STATE_PATH, 'utf8')) as RawState;
  return {
    configured_at: rawState.configured_at,
    livekit_project_name: rawState.livekit_project_name,
    livekit_url: rawState.livekit_url,
    agent_name: rawState.agent_name,
    bridge_provider: normalizeBridgeProvider(rawState.bridge_provider ?? 'claude'),
    claude_workdir: rawState.claude_workdir,
    phone: rawState.phone
      ? {
          number: rawState.phone.number,
          pin: rawState.phone.pin,
          dispatchRuleName:
            rawState.phone.dispatchRuleName ?? rawState.phone.dispatch_rule_name ?? '',
          dispatchRuleId: rawState.phone.dispatchRuleId ?? rawState.phone.dispatch_rule_id ?? '',
        }
      : null,
  };
}

function requireTools(...tools: string[]): void {
  const missing = tools.filter((tool) => !Bun.which(tool));
  if (missing.length > 0) {
    throw new BridgeCliError(`missing required tools: ${missing.join(', ')}`);
  }
}

async function selectBridgeProvider(
  ui: ReturnType<typeof createPrompter>,
  agentEnv: Record<string, string>,
  existingState: SetupState | null
): Promise<string> {
  const provider = normalizeBridgeProvider(
    agentEnv.BRIDGE_CLI_PROVIDER ?? existingState?.bridge_provider ?? 'claude'
  );
  const options = ['Claude Code', 'Codex CLI'];
  const selection = await ui.selectOption(
    'Choose the coding CLI',
    options,
    provider === 'claude' ? 0 : 1
  );
  return selection === 0 ? 'claude' : 'codex';
}

function normalizeBridgeProvider(value: string): string {
  return value.trim().toLowerCase() === 'codex' ? 'codex' : 'claude';
}

function formatBridgeProvider(provider: string): string {
  return provider === 'codex' ? 'Codex CLI' : 'Claude Code';
}

function bridgeAuthCommand(provider: string): string[] {
  return provider === 'codex'
    ? ['codex', 'login', 'status']
    : ['claude', 'auth', 'status'];
}

function installRepoLineSkill(
  provider: string,
  workdir: string
): { method: 'existing' | 'symlink' | 'copy'; targetPath: string } {
  if (!existsSync(REPOLINE_SKILL_SOURCE_PATH)) {
    throw new BridgeCliError(`RepoLine skill source not found: ${REPOLINE_SKILL_SOURCE_PATH}`);
  }

  const targetRoot = join(workdir, ...projectSkillPath(provider));
  const targetPath = join(targetRoot, REPOLINE_SKILL_NAME);
  mkdirSync(targetRoot, { recursive: true });

  if (existsSync(targetPath)) {
    if (!isRepoLineSkillDirectory(targetPath, REPOLINE_SKILL_NAME)) {
      throw new BridgeCliError(`existing path is not a RepoLine skill install: ${targetPath}`);
    }
    return { method: 'existing', targetPath };
  }

  try {
    symlinkSync(REPOLINE_SKILL_SOURCE_DIR, targetPath, 'dir');
    return { method: 'symlink', targetPath };
  } catch {
    cpSync(REPOLINE_SKILL_SOURCE_DIR, targetPath, { recursive: true });
    return { method: 'copy', targetPath };
  }
}

function projectSkillPath(provider: string): string[] {
  return provider === 'codex' ? ['.agents', 'skills'] : ['.claude', 'skills'];
}

function isRepoLineSkillDirectory(pathValue: string, skillName: string): boolean {
  const skillPath = join(pathValue, 'SKILL.md');
  if (!existsSync(skillPath)) {
    return false;
  }

  const contents = readFileSync(skillPath, 'utf8');
  return new RegExp(`(^|\\n)name:\\s*${skillName}(\\n|$)`).test(contents);
}

function checkCommandAvailable(name: string): { name: string; ok: boolean; detail: string } {
  const pathValue = Bun.which(name);
  return {
    name: `Command \`${name}\``,
    ok: Boolean(pathValue),
    detail: pathValue ?? 'not found',
  };
}

function checkFileExists(name: string, pathValue: string): { name: string; ok: boolean; detail: string } {
  return {
    name,
    ok: existsSync(pathValue),
    detail: pathValue,
  };
}

function checkEnvKey(
  label: string,
  env: Record<string, string>,
  key: string
): { name: string; ok: boolean; detail: string } {
  const value = env[key] ?? '';
  return {
    name: `${label} ${key}`,
    ok: value.length > 0,
    detail: value.length > 0 ? 'set' : 'missing',
  };
}

function checkAnyEnvKey(
  name: string,
  env: Record<string, string>,
  keys: string[],
  fallbackValue?: string
): { name: string; ok: boolean; detail: string } {
  const matchedKey = keys.find((key) => (env[key] ?? '').length > 0);
  if (matchedKey) {
    return {
      name,
      ok: true,
      detail: `${matchedKey} set`,
    };
  }

  if ((fallbackValue ?? '').length > 0) {
    return {
      name,
      ok: true,
      detail: `defaulting to ${fallbackValue}`,
    };
  }

  return {
    name,
    ok: false,
    detail: `missing (${keys.join(' or ')})`,
  };
}

function checkInstalledRepoLineSkill(
  provider: string,
  workdir: string,
  skillName: string
): { name: string; ok: boolean; detail: string } {
  const targetPath = workdir
    ? join(workdir, ...projectSkillPath(provider), skillName)
    : join('<missing-workdir>', ...projectSkillPath(provider), skillName);

  if (!workdir) {
    return {
      name: 'RepoLine skill install',
      ok: false,
      detail: 'missing workdir',
    };
  }

  if (!isRepoLineSkillDirectory(targetPath, skillName)) {
    return {
      name: 'RepoLine skill install',
      ok: false,
      detail: `missing ${targetPath}`,
    };
  }

  let detail = targetPath;
  try {
    if (lstatSync(targetPath).isSymbolicLink()) {
      detail = `${targetPath} (symlink)`;
    }
  } catch {}

  return {
    name: 'RepoLine skill install',
    ok: true,
    detail,
  };
}

function runStatusCheck(
  name: string,
  cmd: string[],
  cwd: string,
  envOverrides?: Record<string, string | null>
): { name: string; ok: boolean; detail: string } {
  try {
    runChecked(cmd, {
      cwd,
      captureOutput: true,
      envOverrides,
    });
    return { name, ok: true, detail: 'ok' };
  } catch (error) {
    return {
      name,
      ok: false,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

function checkPhoneState(state: SetupState): { name: string; ok: boolean; detail: string } {
  if (!state.phone) {
    return { name: 'Phone number wiring', ok: true, detail: 'not configured' };
  }

  try {
    const dispatch = selectDispatchRule(state.livekit_project_name, state.phone.dispatchRuleName);
    if (!dispatch) {
      return { name: 'Phone number wiring', ok: false, detail: 'dispatch rule not found' };
    }
    if (!(dispatch.inboundNumbers ?? []).includes(state.phone.number)) {
      return {
        name: 'Phone number wiring',
        ok: false,
        detail: 'dispatch rule is not scoped to the configured number',
      };
    }
    return {
      name: 'Phone number wiring',
      ok: true,
      detail: state.phone.number,
    };
  } catch (error) {
    return {
      name: 'Phone number wiring',
      ok: false,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

function runChecked(
  cmd: string[],
  options: {
    cwd: string;
    captureOutput?: boolean;
    stdinText?: string;
    envOverrides?: Record<string, string | null>;
  }
): { stdout: string; stderr: string } {
  const result = spawnSync(cmd[0], cmd.slice(1), {
    cwd: options.cwd,
    env: buildEnv(options.envOverrides),
    input: options.stdinText,
    encoding: 'utf8',
    stdio: options.captureOutput ? 'pipe' : 'inherit',
  });

  if (result.status !== 0) {
    const stderr = (result.stderr ?? '').trim();
    const stdout = (result.stdout ?? '').trim();
    throw new BridgeCliError(stderr || stdout || `command failed: ${cmd.join(' ')}`);
  }

  return {
    stdout: result.stdout ?? '',
    stderr: result.stderr ?? '',
  };
}

function runJsonCommand(
  cmd: string[],
  options: {
    cwd: string;
    stdinText?: string;
    envOverrides?: Record<string, string | null>;
  }
): unknown {
  const result = runChecked(cmd, {
    cwd: options.cwd,
    captureOutput: true,
    stdinText: options.stdinText,
    envOverrides: options.envOverrides,
  });
  const stdout = result.stdout.trim();
  if (!stdout) {
    return {};
  }

  for (let index = 0; index < stdout.length; index += 1) {
    if (stdout[index] !== '{' && stdout[index] !== '[') {
      continue;
    }
    const candidate = stdout.slice(index);
    try {
      return JSON.parse(candidate);
    } catch {
      continue;
    }
  }

  throw new BridgeCliError(`expected JSON from \`${cmd.join(' ')}\`, got: ${result.stdout}`);
}

function buildEnv(overrides?: Record<string, string | null>): NodeJS.ProcessEnv {
  const env = { ...process.env };
  if (!overrides) {
    return env;
  }

  for (const [key, value] of Object.entries(overrides)) {
    if (value === null) {
      delete env[key];
    } else {
      env[key] = value;
    }
  }
  return env;
}

function resolveHome(pathValue: string): string {
  if (pathValue.startsWith('~/')) {
    return resolve(process.env.HOME ?? '', pathValue.slice(2));
  }
  return resolve(pathValue);
}

function isDirectory(pathValue: string): boolean {
  try {
    return statSync(pathValue).isDirectory();
  } catch {
    return false;
  }
}

function formatPhoneNumberOption(number: PhoneNumberRecord): string {
  const location = [number.locality, number.region].filter(Boolean).join(', ');
  return location ? `${number.e164Format} (${location})` : number.e164Format;
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-|-$/g, '');
}

function createPrompter() {
  const ui = createInterface({
    input: process.stdin,
    output: process.stdout,
  });

  return {
    async promptText(prompt: string, defaultValue?: string): Promise<string> {
      while (true) {
        const suffix = defaultValue ? ` [${defaultValue}]` : '';
        const answer = (await ui.question(`${prompt}${suffix}: `)).trim();
        if (answer) {
          return answer;
        }
        if (defaultValue !== undefined) {
          return defaultValue;
        }
        console.log('A value is required.');
      }
    },

    async promptBool(prompt: string, defaultValue: boolean): Promise<boolean> {
      const hint = defaultValue ? 'Y/n' : 'y/N';
      while (true) {
        const answer = (await ui.question(`${prompt} [${hint}]: `)).trim().toLowerCase();
        if (!answer) {
          return defaultValue;
        }
        if (answer === 'y' || answer === 'yes') {
          return true;
        }
        if (answer === 'n' || answer === 'no') {
          return false;
        }
        console.log('Enter y or n.');
      }
    },

    async selectOption(prompt: string, options: string[], defaultIndex = 0): Promise<number> {
      if (options.length === 0) {
        throw new BridgeCliError(`no options available for: ${prompt}`);
      }
      console.log(prompt);
      for (const [index, option] of options.entries()) {
        const marker = index === defaultIndex ? ' (default)' : '';
        console.log(`  ${index + 1}. ${option}${marker}`);
      }
      while (true) {
        const answer = (await ui.question('Select an option by number: ')).trim();
        if (!answer) {
          return defaultIndex;
        }
        const numeric = Number(answer);
        if (Number.isInteger(numeric) && numeric >= 1 && numeric <= options.length) {
          return numeric - 1;
        }
        console.log(`Enter a number between 1 and ${options.length}.`);
      }
    },

    close(): void {
      ui.close();
    },
  };
}
