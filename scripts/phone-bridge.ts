#!/usr/bin/env bun

import {
  cancel as clackCancel,
  confirm as clackConfirm,
  intro,
  isCancel,
  note,
  outro,
  select as clackSelect,
  spinner as clackSpinner,
  text as clackText,
} from '@clack/prompts';
import { spawn, spawnSync, type ChildProcess } from 'node:child_process';
import {
  closeSync,
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  openSync,
  readdirSync,
  readFileSync,
  symlinkSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  REPOLINE_SKILL_NAME,
  REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
  loadEnvFile,
  loadSetupState,
  normalizeBridgeProvider,
  saveSetupState,
  type BridgeProvider,
  type PhoneConfig,
  type SetupState,
  writeBridgeEnvFiles,
} from './bridge-runtime-config';

type LiveKitProject = {
  name: string;
  url: string;
  apiKey: string;
  apiSecret: string;
  projectId: string | null;
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

type PromptOption = {
  label: string;
  hint?: string;
};

const __filename = fileURLToPath(import.meta.url);
const REPO_ROOT = resolve(dirname(__filename), '..');
const AGENT_DIR = join(REPO_ROOT, 'agent');
const FRONTEND_DIR = join(REPO_ROOT, 'frontend');
const AGENT_ENV_PATH = join(AGENT_DIR, '.env.local');
const FRONTEND_ENV_PATH = join(FRONTEND_DIR, '.env.local');
const STATE_DIR = join(REPO_ROOT, '.bridge');
const STATE_PATH = join(STATE_DIR, 'state.json');
const RUNTIME_LOG_DIR = join(STATE_DIR, 'runtime');
const AGENT_DEV_LOG_PATH = join(RUNTIME_LOG_DIR, 'agent-dev.log');
const AGENT_LIVE_LOG_PATH = join(RUNTIME_LOG_DIR, 'agent-live.log');
const FRONTEND_DEV_LOG_PATH = join(RUNTIME_LOG_DIR, 'frontend-dev.log');
const FRONTEND_LIVE_LOG_PATH = join(RUNTIME_LOG_DIR, 'frontend-live.log');
const LATEST_CALL_SUMMARY_PATH = join(AGENT_DIR, 'logs', 'latest-call.md');
const CALL_HISTORY_DIR = join(AGENT_DIR, 'logs', 'calls');
const PHONE_NUMBER_STATUS_ACTIVE = 'PHONE_NUMBER_STATUS_ACTIVE';
const REPOLINE_SKILL_SOURCE_DIR = join(REPO_ROOT, 'skills', REPOLINE_SKILL_NAME);
const REPOLINE_SKILL_SOURCE_PATH = join(REPOLINE_SKILL_SOURCE_DIR, 'SKILL.md');
const REPOLINE_CURSOR_RULE_SOURCE_PATH = join(REPOLINE_SKILL_SOURCE_DIR, 'cursor-rule.mdc');
const REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_DIR = join(
  REPO_ROOT,
  'skills',
  REPOLINE_TTS_PRONUNCIATION_SKILL_NAME
);
const REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_PATH = join(
  REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_DIR,
  'SKILL.md'
);
const REPOLINE_TTS_PRONUNCIATION_NOTES_SOURCE_PATH = join(
  REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_DIR,
  'references',
  'PROVIDER_NOTES.md'
);

class BridgeCliError extends Error {}

const command = process.argv[2];

if (!command || !['setup', 'dev', 'live', 'doctor'].includes(command)) {
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
    case 'live':
      await liveCommand();
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
  console.log(`Usage: bun run ${basename(__filename)} <setup|dev|live|doctor>`);
}

async function setupCommand(): Promise<void> {
  intro('RepoLine');
  note(
    'This will write local env files, install the RepoLine voice and pronunciation skills into your selected repo, install dependencies, and optionally wire a project phone number.',
    'Setup'
  );

  requireTools('lk', 'uv', 'bun');

  const agentEnv = loadEnvFile(AGENT_ENV_PATH);
  const frontendEnv = loadEnvFile(FRONTEND_ENV_PATH);
  const existingState = loadSetupState(STATE_PATH);

  const ui = createPrompter();
  try {
    const bridgeProvider = await selectBridgeProvider(ui, agentEnv, existingState);
    requireTools(providerExecutable(bridgeProvider));
    await ensureProviderAuthenticated(ui, bridgeProvider);

    const project = await selectLiveKitProject(ui, agentEnv);
    const projectNumbers = listPhoneNumbers(project.name);
    const agentNameDefault =
      agentEnv.LIVEKIT_AGENT_NAME ??
      frontendEnv.AGENT_NAME ??
      existingState?.agent_name ??
      'clawdbot-agent';
    const agentName = await ui.promptText('LiveKit agent name', agentNameDefault);
    const workdir = await selectWorkdir(ui, agentEnv.BRIDGE_WORKDIR ?? existingState?.workdir ?? null);
    const ttsModel = agentEnv.LIVEKIT_TTS_MODEL ?? 'cartesia/sonic-3';
    const ttsVoice = agentEnv.LIVEKIT_TTS_VOICE ?? '9626c31c-bec5-4cca-baa8-f8ba9e84c8bc';
    const skillInstall = installRepoLineSkill(bridgeProvider, workdir);
    const pronunciationSkillInstall = installRepoLineTtsPronunciationSkill(
      bridgeProvider,
      workdir,
      ttsModel,
      ttsVoice
    );

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

    writeBridgeEnvFiles({
      agentEnvPath: AGENT_ENV_PATH,
      frontendEnvPath: FRONTEND_ENV_PATH,
      project,
      agentName,
      bridgeProvider,
      workdir,
      existingAgentEnv: agentEnv,
      existingFrontendEnv: frontendEnv,
    });

    saveSetupState(STATE_PATH, {
      configured_at: new Date().toISOString(),
      livekit_project_name: project.name,
      livekit_url: project.url,
      agent_name: agentName,
      bridge_provider: bridgeProvider,
      workdir,
      phone: phoneConfig,
    });

    const installSpinner = clackSpinner();
    installSpinner.start('Installing dependencies and pre-downloading agent assets');
    runChecked(['uv', 'sync'], {
      cwd: AGENT_DIR,
      captureOutput: true,
      envOverrides: { VIRTUAL_ENV: null },
    });
    runChecked(['uv', 'run', 'python', 'src/agent.py', 'download-files'], {
      cwd: AGENT_DIR,
      captureOutput: true,
      envOverrides: { VIRTUAL_ENV: null },
    });
    runChecked(['bun', 'install'], {
      cwd: FRONTEND_DIR,
      captureOutput: true,
    });
    installSpinner.stop('Dependencies installed');

    const summaryLines = [
      `LiveKit project: ${project.name}`,
      `Coding CLI: ${formatBridgeProvider(bridgeProvider)}`,
      `Workdir: ${workdir}`,
      `RepoLine instructions: ${skillInstall.targetPath} (${skillInstall.method})`,
      `TTS pronunciation notes: ${pronunciationSkillInstall.targetPath} (${pronunciationSkillInstall.method})`,
      `Agent name: ${agentName}`,
    ];
    if (phoneConfig) {
      summaryLines.push(`Dispatch rule: ${phoneConfig.dispatchRuleName}`);
    }
    note(summaryLines.join('\n'), 'Setup complete');
    if (phoneConfig) {
      note(formatPhoneInstructions(phoneConfig), 'Call In');
    }
    outro('Starting RepoLine live...');
  } finally {
    ui.close();
  }

  await liveCommand();
}

async function devCommand(): Promise<void> {
  await runRuntimeCommand('dev');
}

async function liveCommand(): Promise<void> {
  await runRuntimeCommand('live');
}

async function runRuntimeCommand(mode: 'dev' | 'live'): Promise<void> {
  if (!existsSync(AGENT_ENV_PATH) || !existsSync(FRONTEND_ENV_PATH)) {
    throw new BridgeCliError('run `bun run setup` first.');
  }

  requireTools('uv', 'bun');
  const state = loadSetupState(STATE_PATH);
  prepareCallSummaryArtifacts();

  const processes = [
    spawnProcess(['uv', 'run', 'python', 'src/agent.py', mode === 'live' ? 'start' : 'dev'], {
      cwd: AGENT_DIR,
      label: mode === 'live' ? 'RepoLine agent (live)' : 'RepoLine agent (dev)',
      logPath: mode === 'live' ? AGENT_LIVE_LOG_PATH : AGENT_DEV_LOG_PATH,
      envOverrides: { PYTHONUNBUFFERED: '1', VIRTUAL_ENV: null },
    }),
    spawnProcess(['bun', 'run', 'dev:network'], {
      cwd: FRONTEND_DIR,
      label: mode === 'live' ? 'RepoLine frontend (live)' : 'RepoLine frontend (dev)',
      logPath: mode === 'live' ? FRONTEND_LIVE_LOG_PATH : FRONTEND_DEV_LOG_PATH,
    }),
  ];
  printRuntimeInfo(state, mode);

  let settled = false;
  const terminateAll = (signal: NodeJS.Signals) => {
    for (const processInfo of processes) {
      const child = processInfo.child;
      if (child.exitCode === null) {
        child.kill(signal);
      }
    }
  };

  const cleanupAndExit = async (code: number, childSignal: NodeJS.Signals) => {
    if (settled) {
      return;
    }
    settled = true;
    terminateAll(childSignal);
    await Bun.sleep(500);
    for (const processInfo of processes) {
      const child = processInfo.child;
      if (child.exitCode === null) {
        child.kill('SIGKILL');
      }
    }
    process.exit(code);
  };

  process.once('SIGINT', () => void cleanupAndExit(0, 'SIGINT'));
  process.once('SIGTERM', () => void cleanupAndExit(0, 'SIGTERM'));

  await Promise.race(
    processes.map(
      (processInfo) =>
        new Promise<void>((resolve) => {
          const child = processInfo.child;
          child.once('exit', (code) => {
            if (!settled && (code ?? 0) !== 0) {
              console.error(
                `${processInfo.label} exited with code ${code ?? 'unknown'}. See ${processInfo.logPath}`
              );
            }
            void cleanupAndExit(code ?? 1, 'SIGTERM');
            resolve();
          });
        })
    )
  );
}

function printRuntimeInfo(state: SetupState | null, mode: 'dev' | 'live'): void {
  const lines = [
    mode === 'live' ? 'RepoLine is running in live mode.' : 'RepoLine is running in dev mode.',
    '',
  ];

  if (state?.phone) {
    lines.push(`Call this number: ${state.phone.number}`);
    lines.push(`Enter PIN ${state.phone.pin}, then press #`);
    lines.push('');
  }

  if (mode === 'live') {
    lines.push('Agent watcher: disabled');
    lines.push('Recommended while other agents are editing the repo.');
  } else {
    lines.push('WARNING: active calls may reset when watched files change.');
    lines.push('Agent watcher: enabled');
    lines.push('Use this only when you want hot reloads during local development.');
  }
  lines.push('');
  lines.push('Browser UI: http://localhost:3000');
  lines.push(`Latest call summary: ${LATEST_CALL_SUMMARY_PATH}`);
  lines.push(`Call history: ${CALL_HISTORY_DIR}`);
  lines.push(`Agent log: ${mode === 'live' ? AGENT_LIVE_LOG_PATH : AGENT_DEV_LOG_PATH}`);
  lines.push(`Frontend log: ${mode === 'live' ? FRONTEND_LIVE_LOG_PATH : FRONTEND_DEV_LOG_PATH}`);
  lines.push('');
  lines.push('Press Ctrl+C to stop.');

  console.log(lines.join('\n'));
}

function prepareCallSummaryArtifacts(): void {
  mkdirSync(CALL_HISTORY_DIR, { recursive: true });
  if (!existsSync(LATEST_CALL_SUMMARY_PATH)) {
    writeFileSync(
      LATEST_CALL_SUMMARY_PATH,
      '# RepoLine Call Summary\n\nNo calls captured yet.\n',
    );
  }
}

function doctorCommand(): void {
  const checks: Array<{ name: string; ok: boolean; detail: string }> = [];

  checks.push(checkFileExists('Agent env', AGENT_ENV_PATH));
  checks.push(checkFileExists('Frontend env', FRONTEND_ENV_PATH));
  checks.push(checkFileExists('Frontend Bun lockfile', join(FRONTEND_DIR, 'bun.lock')));
  checks.push(checkFileExists('RepoLine voice skill source', REPOLINE_SKILL_SOURCE_PATH));
  checks.push(checkFileExists('RepoLine Cursor rule source', REPOLINE_CURSOR_RULE_SOURCE_PATH));
  checks.push(
    checkFileExists(
      'RepoLine TTS pronunciation skill source',
      REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_PATH
    )
  );
  checks.push(
    checkFileExists(
      'RepoLine TTS pronunciation notes source',
      REPOLINE_TTS_PRONUNCIATION_NOTES_SOURCE_PATH
    )
  );

  const agentEnv = loadEnvFile(AGENT_ENV_PATH);
  const frontendEnv = loadEnvFile(FRONTEND_ENV_PATH);
  const state = loadSetupState(STATE_PATH);
  const bridgeProviderRaw = agentEnv.BRIDGE_CLI_PROVIDER ?? '';
  const bridgeProvider = bridgeProviderRaw ? normalizeBridgeProvider(bridgeProviderRaw) : null;
  const workdir = agentEnv.BRIDGE_WORKDIR ?? '';
  const repolineSkillName = agentEnv.REPOLINE_SKILL_NAME ?? '';
  const repolineTtsPronunciationSkillName =
    agentEnv.REPOLINE_TTS_PRONUNCIATION_SKILL_NAME ?? '';

  const requiredTools = bridgeProvider
    ? [providerExecutable(bridgeProvider), 'lk', 'uv', 'bun']
    : ['lk', 'uv', 'bun'];
  for (const tool of requiredTools) {
    checks.push(checkCommandAvailable(tool));
  }

  for (const key of ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'LIVEKIT_AGENT_NAME']) {
    checks.push(checkEnvKey('Agent env', agentEnv, key));
  }
  checks.push(checkEnvKey('Agent env', agentEnv, 'BRIDGE_CLI_PROVIDER'));
  checks.push(checkEnvKey('Agent env', agentEnv, 'BRIDGE_WORKDIR'));
  checks.push(checkEnvKey('Agent env', agentEnv, 'REPOLINE_SKILL_NAME'));
  checks.push(checkEnvKey('Agent env', agentEnv, 'REPOLINE_TTS_PRONUNCIATION_SKILL_NAME'));

  for (const key of ['LIVEKIT_URL', 'LIVEKIT_API_KEY', 'LIVEKIT_API_SECRET', 'AGENT_NAME']) {
    checks.push(checkEnvKey('Frontend env', frontendEnv, key));
  }

  if (bridgeProvider) {
    const authStatus = getProviderAuthStatus(bridgeProvider);
    checks.push({
      name: `${formatBridgeProvider(bridgeProvider)} auth`,
      ok: authStatus.ok,
      detail: authStatus.detail,
    });
  }
  checks.push(
    runStatusCheck('Agent dependencies', ['uv', 'sync', '--check'], AGENT_DIR, {
      VIRTUAL_ENV: null,
    })
  );
  checks.push(runStatusCheck('Frontend dependencies', ['bun', 'install', '--frozen-lockfile'], FRONTEND_DIR));
  checks.push(
    checkInstalledRepoLineSkill(
      bridgeProvider,
      workdir,
      repolineSkillName,
      'RepoLine instructions install'
    )
  );
  checks.push(
    checkInstalledRepoLineSkill(
      bridgeProvider,
      workdir,
      repolineTtsPronunciationSkillName,
      'RepoLine TTS pronunciation install'
    )
  );

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
    label: string;
    logPath: string;
    envOverrides?: Record<string, string | null>;
  }
): { child: ChildProcess; label: string; logPath: string } {
  mkdirSync(dirname(options.logPath), { recursive: true });
  writeFileSync(
    options.logPath,
    `# ${options.label}\n# Command: ${cmd.join(' ')}\n# Started: ${new Date().toISOString()}\n\n`
  );
  const fd = openSync(options.logPath, 'a');
  const child = spawn(cmd[0], cmd.slice(1), {
    cwd: options.cwd,
    stdio: ['ignore', fd, fd],
    env: buildEnv(options.envOverrides),
  });
  child.once('exit', () => {
    closeSync(fd);
  });
  return {
    child,
    label: options.label,
    logPath: options.logPath,
  };
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
    projects.map((project) => ({
      label: project.name,
      hint: project.url,
    })),
    defaultIndex
  );
  return projects[selection];
}

async function selectWorkdir(
  ui: ReturnType<typeof createPrompter>,
  existingWorkdir: string | null
): Promise<string> {
  const candidates = discoverRepoCandidates(existingWorkdir);
  const options = candidates.map((candidate) => ({
    label: basename(candidate),
    hint: candidate,
  }));
  options.push({
    label: 'Enter a path manually',
    hint: 'Type any absolute path or ~/ path',
  });

  const selection = await ui.selectOption('Choose the coding CLI workdir', options, 0);
  if (selection === candidates.length) {
    while (true) {
      const value = await ui.promptText('Path to the repo', existingWorkdir ?? undefined);
      const resolved = resolveHome(value);
      if (isDirectory(resolved)) {
        return resolved;
      }
      note(`Path does not exist: ${resolved}`, 'Try again');
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
        captureOutput: true,
        stdinText: JSON.stringify(dispatchPayload),
      }
    );
  } else {
    runChecked(['lk', '--project', project.name, 'sip', 'dispatch', 'create', '-'], {
      cwd: REPO_ROOT,
      captureOutput: true,
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
    note(`Using the only active project number: ${phoneNumber}`, 'Phone number');
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
    numbers.map((item) => ({
      label: item.e164Format,
      hint: formatPhoneNumberOption(item),
    })),
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
    note('PIN must be exactly 4 digits.', 'Try again');
  }
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
): Promise<BridgeProvider> {
  const provider = normalizeBridgeProvider(
    agentEnv.BRIDGE_CLI_PROVIDER ?? existingState?.bridge_provider ?? 'claude'
  );
  const options = [
    {
      label: 'Claude Code',
      hint: 'Uses claude auth and installs the skill into .claude/skills',
    },
    {
      label: 'Codex CLI',
      hint: 'Uses codex login and installs the skill into .agents/skills',
    },
    {
      label: 'Cursor Agent',
      hint: 'Uses cursor-agent auth and installs the rule into .cursor/rules',
    },
  ];
  const selection = await ui.selectOption(
    'Choose the coding CLI',
    options,
    provider === 'claude' ? 0 : provider === 'codex' ? 1 : 2
  );
  if (selection === 0) {
    return 'claude';
  }
  if (selection === 1) {
    return 'codex';
  }
  return 'cursor';
}

function formatBridgeProvider(provider: BridgeProvider): string {
  if (provider === 'codex') {
    return 'Codex CLI';
  }
  if (provider === 'cursor') {
    return 'Cursor Agent';
  }
  return 'Claude Code';
}

function providerExecutable(provider: BridgeProvider): string {
  if (provider === 'cursor') {
    return 'cursor-agent';
  }
  return provider;
}

function bridgeAuthCommand(provider: BridgeProvider): string[] {
  if (provider === 'codex') {
    return ['codex', 'login', 'status'];
  }
  if (provider === 'cursor') {
    return ['cursor-agent', 'status'];
  }
  return ['claude', 'auth', 'status'];
}

function bridgeLoginCommand(provider: BridgeProvider): string[] {
  if (provider === 'codex') {
    return ['codex', 'login'];
  }
  if (provider === 'cursor') {
    return ['cursor-agent', 'login'];
  }
  return ['claude', 'auth', 'login'];
}

function getProviderAuthStatus(provider: BridgeProvider): { ok: boolean; detail: string } {
  try {
    const result = runChecked(bridgeAuthCommand(provider), {
      cwd: REPO_ROOT,
      captureOutput: true,
    });
    const output = stripAnsi(`${result.stdout}\n${result.stderr}`).trim();

    if (provider === 'claude') {
      try {
        const payload = JSON.parse(output) as { loggedIn?: boolean; email?: string | null };
        if (payload.loggedIn === true) {
          return { ok: true, detail: payload.email ?? 'ok' };
        }
        if (payload.loggedIn === false) {
          return { ok: false, detail: output || 'Not logged in' };
        }
      } catch {}
    }

    const normalizedOutput = output.toLowerCase();
    if (
      normalizedOutput.includes('not logged in') ||
      normalizedOutput.includes('not authenticated') ||
      normalizedOutput.includes('signed out') ||
      normalizedOutput.includes('login required')
    ) {
      return { ok: false, detail: output || 'Not logged in' };
    }

    if (normalizedOutput.includes('logged in')) {
      return { ok: true, detail: output || 'ok' };
    }

    return { ok: true, detail: output || 'ok' };
  } catch (error) {
    return {
      ok: false,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

async function ensureProviderAuthenticated(
  ui: ReturnType<typeof createPrompter>,
  provider: BridgeProvider
): Promise<void> {
  const status = getProviderAuthStatus(provider);
  if (status.ok) {
    return;
  }

  note(
    `${formatBridgeProvider(provider)} is not authenticated yet.\n${status.detail}`,
    'Auth required'
  );

  const shouldLogin = await ui.promptBool(`Run ${formatBridgeProvider(provider)} login now?`, true);
  if (!shouldLogin) {
    throw new BridgeCliError(
      `${formatBridgeProvider(provider)} authentication is required before setup can continue.`
    );
  }

  note(
    'Complete the login flow in this terminal or the browser window it opens, then setup will continue.',
    'Login'
  );
  runChecked(bridgeLoginCommand(provider), {
    cwd: REPO_ROOT,
    captureOutput: false,
  });

  const refreshedStatus = getProviderAuthStatus(provider);
  if (!refreshedStatus.ok) {
    throw new BridgeCliError(
      `${formatBridgeProvider(provider)} still is not authenticated: ${refreshedStatus.detail}`
    );
  }
}

function installRepoLineSkill(
  provider: BridgeProvider,
  workdir: string
): { method: 'existing' | 'symlink' | 'copy' | 'generated'; targetPath: string } {
  if (!existsSync(REPOLINE_SKILL_SOURCE_PATH)) {
    throw new BridgeCliError(`RepoLine skill source not found: ${REPOLINE_SKILL_SOURCE_PATH}`);
  }

  if (provider === 'cursor') {
    if (!existsSync(REPOLINE_CURSOR_RULE_SOURCE_PATH)) {
      throw new BridgeCliError(
        `RepoLine Cursor rule source not found: ${REPOLINE_CURSOR_RULE_SOURCE_PATH}`
      );
    }

    const targetRoot = join(workdir, ...projectSkillPath(provider));
    const targetPath = join(targetRoot, `${REPOLINE_SKILL_NAME}.mdc`);
    mkdirSync(targetRoot, { recursive: true });

    if (existsSync(targetPath)) {
      if (!isRepoLineCursorRule(targetPath, REPOLINE_SKILL_NAME)) {
        throw new BridgeCliError(`existing path is not a RepoLine rule install: ${targetPath}`);
      }
      return { method: 'existing', targetPath };
    }

    writeFileSync(targetPath, readFileSync(REPOLINE_CURSOR_RULE_SOURCE_PATH, 'utf8'));
    return { method: 'generated', targetPath };
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

function installRepoLineTtsPronunciationSkill(
  provider: BridgeProvider,
  workdir: string,
  ttsModel: string,
  ttsVoice: string
): { method: 'existing' | 'symlink' | 'copy' | 'generated'; targetPath: string } {
  if (!existsSync(REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_PATH)) {
    throw new BridgeCliError(
      `RepoLine TTS pronunciation skill source not found: ${REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_PATH}`
    );
  }

  if (provider === 'cursor') {
    const targetRoot = join(workdir, ...projectSkillPath(provider));
    const targetPath = join(targetRoot, `${REPOLINE_TTS_PRONUNCIATION_SKILL_NAME}.mdc`);
    mkdirSync(targetRoot, { recursive: true });

    if (existsSync(targetPath)) {
      if (!isRepoLineCursorRule(targetPath, REPOLINE_TTS_PRONUNCIATION_SKILL_NAME)) {
        throw new BridgeCliError(
          `existing path is not a RepoLine TTS pronunciation rule install: ${targetPath}`
        );
      }
      return { method: 'existing', targetPath };
    }

    writeFileSync(targetPath, buildRepoLineTtsPronunciationCursorRule(ttsModel, ttsVoice));
    return { method: 'generated', targetPath };
  }

  const targetRoot = join(workdir, ...projectSkillPath(provider));
  const targetPath = join(targetRoot, REPOLINE_TTS_PRONUNCIATION_SKILL_NAME);
  mkdirSync(targetRoot, { recursive: true });

  if (existsSync(targetPath)) {
    if (!isRepoLineSkillDirectory(targetPath, REPOLINE_TTS_PRONUNCIATION_SKILL_NAME)) {
      throw new BridgeCliError(
        `existing path is not a RepoLine TTS pronunciation skill install: ${targetPath}`
      );
    }
    ensureRepoLineTtsPronunciationNotes(targetPath, ttsModel, ttsVoice, false);
    return { method: 'existing', targetPath };
  }

  cpSync(REPOLINE_TTS_PRONUNCIATION_SKILL_SOURCE_DIR, targetPath, { recursive: true });
  ensureRepoLineTtsPronunciationNotes(targetPath, ttsModel, ttsVoice, true);
  return { method: 'generated', targetPath };
}

function projectSkillPath(provider: BridgeProvider): string[] {
  if (provider === 'codex') {
    return ['.agents', 'skills'];
  }
  if (provider === 'cursor') {
    return ['.cursor', 'rules'];
  }
  return ['.claude', 'skills'];
}

function isRepoLineSkillDirectory(pathValue: string, skillName: string): boolean {
  const skillPath = join(pathValue, 'SKILL.md');
  if (!existsSync(skillPath)) {
    return false;
  }

  const contents = readFileSync(skillPath, 'utf8');
  return new RegExp(`(^|\\n)name:\\s*${skillName}(\\n|$)`).test(contents);
}

function isRepoLineCursorRule(pathValue: string, skillName: string): boolean {
  if (!existsSync(pathValue)) {
    return false;
  }

  const contents = readFileSync(pathValue, 'utf8');
  return (
    pathValue.endsWith(`${skillName}.mdc`) &&
    contents.includes('description: RepoLine') &&
    contents.includes('# RepoLine')
  );
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

function checkInstalledRepoLineSkill(
  provider: BridgeProvider | null,
  workdir: string,
  skillName: string,
  label = 'RepoLine instructions install'
): { name: string; ok: boolean; detail: string } {
  if (!skillName) {
    return {
      name: label,
      ok: false,
      detail: 'missing skill name',
    };
  }

  if (!provider) {
    return {
      name: label,
      ok: false,
      detail: 'missing bridge provider',
    };
  }

  const targetPath = workdir
    ? provider === 'cursor'
      ? join(workdir, ...projectSkillPath(provider), `${skillName}.mdc`)
      : join(workdir, ...projectSkillPath(provider), skillName)
    : provider === 'cursor'
      ? join('<missing-workdir>', ...projectSkillPath(provider), `${skillName}.mdc`)
      : join('<missing-workdir>', ...projectSkillPath(provider), skillName);

  if (!workdir) {
    return {
      name: label,
      ok: false,
      detail: 'missing workdir',
    };
  }

  const installed = provider === 'cursor'
    ? isRepoLineCursorRule(targetPath, skillName)
    : isRepoLineSkillDirectory(targetPath, skillName);

  if (!installed) {
    return {
      name: label,
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
    name: label,
    ok: true,
    detail,
  };
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

function runStatusCheck(
  name: string,
  cmd: string[],
  cwd: string,
  envOverrides?: Record<string, string | null>,
  failurePatterns?: string[]
): { name: string; ok: boolean; detail: string } {
  try {
    const result = runChecked(cmd, {
      cwd,
      captureOutput: true,
      envOverrides,
    });
    const combinedOutput = `${result.stdout}\n${result.stderr}`.trim().toLowerCase();
    if (failurePatterns?.some((pattern) => combinedOutput.includes(pattern.toLowerCase()))) {
      return {
        name,
        ok: false,
        detail: result.stdout.trim() || result.stderr.trim() || 'status check reported a failure',
      };
    }
    return { name, ok: true, detail: 'ok' };
  } catch (error) {
    return {
      name,
      ok: false,
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

function stripAnsi(value: string): string {
  return value.replace(/\u001B\[[0-9;?]*[ -/]*[@-~]/g, '');
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

function formatPhoneInstructions(phone: PhoneConfig): string {
  return [
    `Call this number from your phone now: ${emphasize(phone.number)}`,
    `Enter this PIN: ${emphasize(phone.pin)}`,
    `Then press ${emphasize('#')}`,
  ].join('\n');
}

function emphasize(value: string): string {
  return `\x1b[1m\x1b[36m${value}\x1b[0m`;
}

function createPrompter() {
  return {
    async promptText(prompt: string, defaultValue?: string): Promise<string> {
      const answer = await clackText({
        message: prompt,
        placeholder: defaultValue,
        defaultValue,
        validate(value) {
          if ((value ?? '').trim()) {
            return;
          }
          if (defaultValue !== undefined) {
            return;
          }
          return 'A value is required.';
        },
      });

      return requirePromptValue(answer, defaultValue);
    },

    async promptBool(prompt: string, defaultValue: boolean): Promise<boolean> {
      const answer = await clackConfirm({
        message: prompt,
        initialValue: defaultValue,
        active: 'Yes',
        inactive: 'No',
      });

      return requirePromptValue(answer);
    },

    async selectOption(
      prompt: string,
      options: Array<string | PromptOption>,
      defaultIndex = 0
    ): Promise<number> {
      if (options.length === 0) {
        throw new BridgeCliError(`no options available for: ${prompt}`);
      }
      const answer = await clackSelect({
        message: prompt,
        initialValue: defaultIndex,
        options: options.map((option, index) => {
          const normalized =
            typeof option === 'string'
              ? { label: option, hint: undefined }
              : option;
          return {
            value: index,
            label: normalized.label,
            hint: normalized.hint ?? (index === defaultIndex ? 'Default' : undefined),
          };
        }),
      });

      return requirePromptValue(answer);
    },

    close(): void {
      // Clack prompts manage their own lifecycle.
    },
  };
}

function requirePromptValue<T>(value: T | symbol, defaultValue?: string): T {
  if (isCancel(value)) {
    clackCancel('Setup cancelled.');
    process.exit(0);
  }

  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (trimmed) {
      return trimmed as T;
    }
    if (defaultValue !== undefined) {
      return defaultValue as T;
    }
  }

  return value;
}
