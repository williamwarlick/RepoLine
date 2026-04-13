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
  existsSync,
  mkdirSync,
  openSync,
  readdirSync,
  rmSync,
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
  type BridgeProvider,
  type PhoneConfig,
  type SetupState,
} from './bridge-runtime-config';
import {
  createBridgeInstallationContract,
} from './bridge-installation-contract';
import {
  checkCommandAvailable,
  checkFileExists,
  checkPhoneState,
  commandInstallHint,
  type DispatchRuleRecord,
  type DoctorCheck,
} from './bridge-doctor';

export type LiveKitProject = {
  name: string;
  url: string;
  apiKey: string;
  apiSecret: string;
  projectId: string | null;
};

export type PhoneNumberRecord = {
  id: string;
  e164Format: string;
  areaCode?: string;
  countryCode?: string;
  locality?: string;
  region?: string;
  status?: string;
};

export type SearchablePhoneNumberRecord = {
  e164Format: string;
  areaCode?: string;
  countryCode?: string;
  locality?: string;
  region?: string;
};

type BridgeCommand = 'setup' | 'dev' | 'live' | 'agent' | 'doctor';

type SetupCommandOptions = {
  startLiveAfterSetup: boolean;
  bridgeProvider?: BridgeProvider;
  livekitProjectName?: string;
  workdir?: string;
  agentName?: string;
  setupPhone?: boolean;
};

type ParsedCliArgs = {
  command: BridgeCommand | null;
  setupOptions: SetupCommandOptions;
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
const FRONTEND_PORT = 3000;
const DEFAULT_FRONTEND_HOST = '127.0.0.1';
const PHONE_NUMBER_STATUS_ACTIVE = 'PHONE_NUMBER_STATUS_ACTIVE';
const LIVEKIT_PHONE_NUMBER_GUIDANCE_DATE = 'April 11, 2026';
const BOOTSTRAP_SCRIPT_PATH = join(REPO_ROOT, 'scripts', 'bootstrap.sh');

class BridgeCliError extends Error {}

refreshKnownPathEntries();

if (import.meta.main) {
  await main(process.argv.slice(2));
}

function printHelp(): void {
  console.log(
    [
      `Usage: bun run ${basename(__filename)} <setup|dev|live|agent|doctor> [options]`,
      '',
      'Setup options:',
      '  --no-start              Configure RepoLine without launching live mode',
      '  --provider <name>       Choose claude, codex, or cursor',
      '  --project <name>        Use a specific linked LiveKit project',
      '  --workdir <path>        Set the coding CLI workdir without prompting',
      '  --agent-name <name>     Set the LiveKit agent name without prompting',
      '  --skip-phone            Skip phone setup without prompting',
    ].join('\n')
  );
}

export function parseCliArgs(argv: string[], env: NodeJS.ProcessEnv = process.env): ParsedCliArgs {
  const [commandRaw, ...rest] = argv;
  const command = isBridgeCommand(commandRaw) ? commandRaw : null;
  const setupOptions: SetupCommandOptions = {
    startLiveAfterSetup: (env.REPOLINE_SETUP_SKIP_LIVE ?? '').trim() !== '1',
  };

  if (command === 'setup') {
    for (let index = 0; index < rest.length; index += 1) {
      const arg = rest[index];
      switch (arg) {
        case '--no-start':
          setupOptions.startLiveAfterSetup = false;
          break;
        case '--skip-phone':
          setupOptions.setupPhone = false;
          break;
        case '--provider':
          setupOptions.bridgeProvider = parseBridgeProviderFlag(
            readRequiredFlagValue('--provider', rest[index + 1])
          );
          index += 1;
          break;
        case '--project':
          setupOptions.livekitProjectName = readRequiredFlagValue('--project', rest[index + 1]);
          index += 1;
          break;
        case '--workdir':
          setupOptions.workdir = readRequiredFlagValue('--workdir', rest[index + 1]);
          index += 1;
          break;
        case '--agent-name':
          setupOptions.agentName = readRequiredFlagValue('--agent-name', rest[index + 1]);
          index += 1;
          break;
        default:
          throw new BridgeCliError(`unknown setup option: ${arg}`);
      }
    }
  }

  return {
    command,
    setupOptions,
  };
}

function readRequiredFlagValue(flag: string, value: string | undefined): string {
  const trimmed = value?.trim();
  if (!trimmed) {
    throw new BridgeCliError(`${flag} requires a value`);
  }
  return trimmed;
}

function parseBridgeProviderFlag(value: string): BridgeProvider {
  const normalized = value.trim().toLowerCase();
  if (normalized === 'claude') {
    return 'claude';
  }
  if (normalized === 'codex') {
    return 'codex';
  }
  if (normalized === 'cursor' || normalized === 'cursor-agent') {
    return 'cursor';
  }
  throw new BridgeCliError(`unsupported --provider value: ${value}`);
}

function isBridgeCommand(value: string | undefined): value is BridgeCommand {
  return value === 'setup' || value === 'dev' || value === 'live' || value === 'agent' || value === 'doctor';
}

export async function main(argv: string[] = process.argv.slice(2)): Promise<void> {
  try {
    const parsed = parseCliArgs(argv);
    if (!parsed.command) {
      printHelp();
      process.exit(argv.length > 0 ? 1 : 0);
    }

    switch (parsed.command) {
      case 'setup':
        await setupCommand(parsed.setupOptions);
        break;
      case 'dev':
        await devCommand();
        break;
      case 'live':
        await liveCommand();
        break;
      case 'agent':
        await agentCommand();
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
}

async function setupCommand(options?: SetupCommandOptions): Promise<void> {
  intro('RepoLine');
  note(
    'This will install missing setup tooling when possible, link LiveKit if needed, write local env files, install the RepoLine voice and pronunciation skills into your selected repo, install dependencies, and optionally wire a project phone number.',
    'Setup'
  );

  const agentEnv = loadEnvFile(AGENT_ENV_PATH);
  const frontendEnv = loadEnvFile(FRONTEND_ENV_PATH);
  const existingState = loadSetupState(STATE_PATH);

  const ui = createPrompter();
  try {
    await ensureToolsAvailable(ui, ['lk', 'uv', 'bun'], 'RepoLine setup');
    const bridgeProvider = await selectBridgeProvider(
      ui,
      agentEnv,
      existingState,
      options?.bridgeProvider
    );
    await ensureToolsAvailable(
      ui,
      [providerExecutable(bridgeProvider)],
      `${formatBridgeProvider(bridgeProvider)} integration`
    );
    await ensureProviderAuthenticated(ui, bridgeProvider);

    const project = await selectLiveKitProject(ui, agentEnv, options?.livekitProjectName);
    const projectNumbers = listPhoneNumbers(project.name);
    const agentNameDefault =
      agentEnv.LIVEKIT_AGENT_NAME ??
      frontendEnv.AGENT_NAME ??
      existingState?.agent_name ??
      'clawdbot-agent';
    const agentName = options?.agentName
      ? noteAndReturn(options.agentName, `Using LiveKit agent name: ${options.agentName}`, 'Agent name')
      : await ui.promptText('LiveKit agent name', agentNameDefault);
    const workdir = await selectWorkdir(
      ui,
      agentEnv.BRIDGE_WORKDIR ?? existingState?.workdir ?? null,
      options?.workdir
    );
    const ttsModel = agentEnv.LIVEKIT_TTS_MODEL ?? 'cartesia/sonic-3';
    const ttsVoice = agentEnv.LIVEKIT_TTS_VOICE ?? '9626c31c-bec5-4cca-baa8-f8ba9e84c8bc';
    const bridgeContract = createBridgeInstallationContract({
      repoRoot: REPO_ROOT,
      provider: bridgeProvider,
      workdir,
      skillName: agentEnv.REPOLINE_SKILL_NAME ?? REPOLINE_SKILL_NAME,
      ttsPronunciationSkillName:
        agentEnv.REPOLINE_TTS_PRONUNCIATION_SKILL_NAME ??
        REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    });
    const { instructions: skillInstall, pronunciation: pronunciationSkillInstall } =
      bridgeContract.materialize({
        ttsModel,
        ttsVoice,
      });

    let phoneConfig: PhoneConfig | null = null;
    const shouldSetupPhone =
      options?.setupPhone ??
      (await ui.promptBool(
        'Configure an inbound phone number now?',
        projectNumbers.length > 0 || existingState?.phone != null
      ));
    if (shouldSetupPhone) {
      phoneConfig = await configurePhone(
        ui,
        project,
        agentName,
        existingState?.phone ?? null,
        projectNumbers
      );
    }

    bridgeContract.persistRuntimeConfig({
      agentEnvPath: AGENT_ENV_PATH,
      frontendEnvPath: FRONTEND_ENV_PATH,
      statePath: STATE_PATH,
      project,
      agentName,
      existingAgentEnv: agentEnv,
      existingFrontendEnv: frontendEnv,
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
    if (options?.startLiveAfterSetup === false) {
      outro('Setup complete. Live mode was skipped because --no-start was set.');
      return;
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

async function agentCommand(): Promise<void> {
  if (!existsSync(AGENT_ENV_PATH)) {
    throw new BridgeCliError('run `bun run setup` first.');
  }

  requireTools('uv');
  const state = loadSetupState(STATE_PATH);
  prepareCallSummaryArtifacts();

  const processInfo = spawnProcess(['uv', 'run', 'python', 'src/agent.py', 'start'], {
    cwd: AGENT_DIR,
    label: 'RepoLine agent (agent-only)',
    logPath: AGENT_LIVE_LOG_PATH,
    envOverrides: { PYTHONUNBUFFERED: '1', VIRTUAL_ENV: null },
  });
  printAgentOnlyRuntimeInfo(state);

  let settled = false;
  const cleanupAndExit = async (code: number, childSignal: NodeJS.Signals) => {
    if (settled) {
      return;
    }
    settled = true;

    if (processInfo.child.exitCode === null) {
      processInfo.child.kill(childSignal);
      await Bun.sleep(500);
    }
    if (processInfo.child.exitCode === null) {
      processInfo.child.kill('SIGKILL');
    }
    process.exit(code);
  };

  process.once('SIGINT', () => void cleanupAndExit(0, 'SIGINT'));
  process.once('SIGTERM', () => void cleanupAndExit(0, 'SIGTERM'));

  await new Promise<void>((resolve) => {
    processInfo.child.once('exit', (code) => {
      if (!settled && (code ?? 0) !== 0) {
        console.error(
          `${processInfo.label} exited with code ${code ?? 'unknown'}. See ${processInfo.logPath}`
        );
      }
      void cleanupAndExit(code ?? 1, 'SIGTERM');
      resolve();
    });
  });
}

async function runRuntimeCommand(mode: 'dev' | 'live'): Promise<void> {
  if (!existsSync(AGENT_ENV_PATH) || !existsSync(FRONTEND_ENV_PATH)) {
    throw new BridgeCliError('run `bun run setup` first.');
  }

  requireTools('uv', 'bun');
  const agentEnv = loadEnvFile(AGENT_ENV_PATH);
  const state = loadSetupState(STATE_PATH);
  const frontendHost = resolveFrontendHost();
  assertSafeRuntimeConfig(agentEnv, frontendHost);
  prepareCallSummaryArtifacts();
  await prepareFrontendRuntime();

  const processes = [
    spawnProcess(['uv', 'run', 'python', 'src/agent.py', mode === 'live' ? 'start' : 'dev'], {
      cwd: AGENT_DIR,
      label: mode === 'live' ? 'RepoLine agent (live)' : 'RepoLine agent (dev)',
      logPath: mode === 'live' ? AGENT_LIVE_LOG_PATH : AGENT_DEV_LOG_PATH,
      envOverrides: { PYTHONUNBUFFERED: '1', VIRTUAL_ENV: null },
    }),
    spawnProcess(
      [
        'bun',
        '--bun',
        'next',
        'dev',
        '--turbopack',
        '--hostname',
        frontendHost,
        '--port',
        String(FRONTEND_PORT),
      ],
      {
      cwd: FRONTEND_DIR,
      label: mode === 'live' ? 'RepoLine frontend (live)' : 'RepoLine frontend (dev)',
      logPath: mode === 'live' ? FRONTEND_LIVE_LOG_PATH : FRONTEND_DEV_LOG_PATH,
      }
    ),
  ];
  printRuntimeInfo(state, mode, frontendHost);

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

type ProcessRecord = {
  pid: number;
  command: string;
};

async function prepareFrontendRuntime(): Promise<void> {
  const existingFrontendProcesses = listRepoFrontendProcesses();
  if (existingFrontendProcesses.length > 0) {
    const processLabel = existingFrontendProcesses.length === 1 ? 'process' : 'processes';
    console.log(
      `Stopping existing RepoLine frontend ${processLabel}: ${existingFrontendProcesses
        .map((processInfo) => processInfo.pid)
        .join(', ')}`
    );
    await stopProcesses(existingFrontendProcesses);
  }

  const portOwner = getListeningProcessOnPort(FRONTEND_PORT);
  if (portOwner) {
    throw new BridgeCliError(
      `localhost:${FRONTEND_PORT} is already in use by ${portOwner.command}. Stop that process and rerun.`
    );
  }

  rmSync(join(FRONTEND_DIR, '.next'), { recursive: true, force: true });
}

function listRepoFrontendProcesses(): ProcessRecord[] {
  const result = spawnSync('ps', ['-axo', 'pid=,command='], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  });
  if (result.status !== 0) {
    return [];
  }

  return result.stdout
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const match = line.match(/^(\d+)\s+(.*)$/);
      if (!match) {
        return null;
      }

      return {
        pid: Number(match[1]),
        command: match[2],
      } satisfies ProcessRecord;
    })
    .filter((record): record is ProcessRecord => {
      if (!record) {
        return false;
      }

      if (!record.command.includes(FRONTEND_DIR)) {
        return false;
      }

      return record.command.includes('next dev') || record.command.includes('start-server.js');
    });
}

function getListeningProcessOnPort(port: number): ProcessRecord | null {
  const pidResult = spawnSync('lsof', ['-nP', `-iTCP:${port}`, '-sTCP:LISTEN', '-t'], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  });
  if (pidResult.status !== 0) {
    return null;
  }

  const pid = Number(pidResult.stdout.split('\n').find(Boolean)?.trim());
  if (!Number.isFinite(pid)) {
    return null;
  }

  const commandResult = spawnSync('ps', ['-p', String(pid), '-o', 'command='], {
    cwd: REPO_ROOT,
    encoding: 'utf8',
  });

  const command =
    commandResult.status === 0
      ? (commandResult.stdout.trim() || `pid ${pid}`)
      : `pid ${pid}`;

  return { pid, command };
}

async function stopProcesses(processes: ProcessRecord[]): Promise<void> {
  const pids = Array.from(new Set(processes.map((processInfo) => processInfo.pid))).filter(Number.isFinite);
  if (pids.length === 0) {
    return;
  }

  spawnSync('kill', ['-TERM', ...pids.map(String)], { cwd: REPO_ROOT });
  await waitForProcessesToExit(pids, 4_000);

  const remainingPids = pids.filter((pid) => isProcessRunning(pid));
  if (remainingPids.length === 0) {
    return;
  }

  spawnSync('kill', ['-KILL', ...remainingPids.map(String)], { cwd: REPO_ROOT });
  await waitForProcessesToExit(remainingPids, 2_000);
}

async function waitForProcessesToExit(pids: number[], timeoutMs: number): Promise<void> {
  const startedAt = Date.now();
  while (Date.now() - startedAt < timeoutMs) {
    if (pids.every((pid) => !isProcessRunning(pid))) {
      return;
    }
    await Bun.sleep(100);
  }
}

function isProcessRunning(pid: number): boolean {
  const result = spawnSync('kill', ['-0', String(pid)], { cwd: REPO_ROOT });
  return result.status === 0;
}

function printRuntimeInfo(
  state: SetupState | null,
  mode: 'dev' | 'live',
  frontendHost: string
): void {
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
  lines.push(`Browser UI: http://${frontendHost}:${FRONTEND_PORT}`);
  if (isRemoteFrontendHost(frontendHost)) {
    lines.push('Remote browser access: enabled');
  } else {
    lines.push('Remote browser access: disabled by default');
  }
  lines.push(`Latest call summary: ${LATEST_CALL_SUMMARY_PATH}`);
  lines.push(`Call history: ${CALL_HISTORY_DIR}`);
  lines.push(`Agent log: ${mode === 'live' ? AGENT_LIVE_LOG_PATH : AGENT_DEV_LOG_PATH}`);
  lines.push(`Frontend log: ${mode === 'live' ? FRONTEND_LIVE_LOG_PATH : FRONTEND_DEV_LOG_PATH}`);
  lines.push('');
  lines.push('Press Ctrl+C to stop.');

  console.log(lines.join('\n'));
}

function printAgentOnlyRuntimeInfo(state: SetupState | null): void {
  const lines = ['RepoLine agent is running in agent-only mode.', ''];

  if (state?.phone) {
    lines.push(`Call this number: ${state.phone.number}`);
    lines.push(`Enter PIN ${state.phone.pin}, then press #`);
    lines.push('');
  }

  lines.push('Use this when the frontend is hosted elsewhere, such as a protected Vercel preview.');
  lines.push(`Latest call summary: ${LATEST_CALL_SUMMARY_PATH}`);
  lines.push(`Call history: ${CALL_HISTORY_DIR}`);
  lines.push(`Agent log: ${AGENT_LIVE_LOG_PATH}`);
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
  const checks: DoctorCheck[] = [];

  checks.push(checkFileExists('Agent env', AGENT_ENV_PATH));
  checks.push(checkFileExists('Frontend env', FRONTEND_ENV_PATH));
  checks.push(checkFileExists('Frontend Bun lockfile', join(FRONTEND_DIR, 'bun.lock')));

  const agentEnv = loadEnvFile(AGENT_ENV_PATH);
  const frontendEnv = loadEnvFile(FRONTEND_ENV_PATH);
  const state = loadSetupState(STATE_PATH);
  const bridgeProviderRaw = agentEnv.BRIDGE_CLI_PROVIDER ?? '';
  const bridgeProvider = bridgeProviderRaw ? normalizeBridgeProvider(bridgeProviderRaw) : null;
  const workdir = agentEnv.BRIDGE_WORKDIR ?? '';
  const repolineSkillName = agentEnv.REPOLINE_SKILL_NAME ?? '';
  const repolineTtsPronunciationSkillName =
    agentEnv.REPOLINE_TTS_PRONUNCIATION_SKILL_NAME ?? '';
  const bridgeContract = createBridgeInstallationContract({
    repoRoot: REPO_ROOT,
    provider: bridgeProvider,
    workdir,
    skillName: repolineSkillName || REPOLINE_SKILL_NAME,
    ttsPronunciationSkillName:
      repolineTtsPronunciationSkillName || REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
  });
  checks.push(...bridgeContract.sourceChecks());

  const requiredTools = bridgeProvider
    ? [providerExecutable(bridgeProvider), 'lk', 'uv', 'bun']
    : ['lk', 'uv', 'bun'];
  for (const tool of requiredTools) {
    checks.push(checkCommandAvailable(tool));
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
  checks.push(...bridgeContract.doctor({ agentEnv, frontendEnv }));

  if (state) {
    checks.push(
      runStatusCheck(
        'LiveKit project link',
        ['lk', '--project', state.livekit_project_name, 'project', 'list', '-j'],
        REPO_ROOT
      )
    );
    if (state.phone) {
      checks.push(
        checkPhoneState(
          state,
          (projectName, dispatchRuleName) =>
            selectDispatchRule(projectName, dispatchRuleName),
          (projectName, phoneNumber) =>
            listPhoneNumbers(projectName).find((item) => item.e164Format === phoneNumber)?.id ?? null
        )
      );
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
  existingAgentEnv: Record<string, string>,
  preferredProjectName?: string
): Promise<LiveKitProject> {
  const projects = await ensureLiveKitProjectsLinked(ui, existingAgentEnv);

  if (preferredProjectName) {
    const match = findLiveKitProject(projects, preferredProjectName);
    if (!match) {
      throw new BridgeCliError(
        `could not find a linked LiveKit project matching "${preferredProjectName}". Available projects: ${projects
          .map((project) => project.name)
          .join(', ')}`
      );
    }
    return noteAndReturn(
      match,
      `Using linked LiveKit project: ${match.name}`,
      'LiveKit project'
    );
  }

  if (projects.length === 1) {
    return noteAndReturn(
      projects[0],
      `Using the only linked LiveKit project: ${projects[0].name}`,
      'LiveKit project'
    );
  }

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

function findLiveKitProject(
  projects: LiveKitProject[],
  preferredProjectName: string
): LiveKitProject | null {
  const normalized = preferredProjectName.trim().toLowerCase();
  return (
    projects.find(
      (project) =>
        project.name.trim().toLowerCase() === normalized ||
        project.url.trim().toLowerCase() === normalized
    ) ?? null
  );
}

async function ensureLiveKitProjectsLinked(
  ui: ReturnType<typeof createPrompter>,
  existingAgentEnv: Record<string, string>
): Promise<LiveKitProject[]> {
  while (true) {
    const { projects, detail } = listConfiguredLiveKitProjects();
    if (projects.length > 0) {
      return projects;
    }

    note(
      [
        'RepoLine could not find any LiveKit projects linked in the `lk` CLI yet.',
        detail,
        'Setup can link your LiveKit Cloud account now, or you can paste one project in manually.',
      ].join('\n'),
      'LiveKit link required'
    );

    const selection = await ui.selectOption(
      'How should RepoLine connect to LiveKit?',
      [
        {
          label: 'Link my LiveKit Cloud account',
          hint: 'Runs `lk cloud auth` and imports your available cloud projects',
        },
        {
          label: 'Add one project manually',
          hint: 'Paste the project URL, API key, and API secret from LiveKit Cloud',
        },
      ],
      0
    );

    if (selection === 0) {
      note(
        'Complete the LiveKit Cloud login flow in this terminal or the browser window it opens. Setup will resume once the CLI has linked your projects.',
        'LiveKit Cloud auth'
      );
      runChecked(['lk', 'cloud', 'auth'], {
        cwd: REPO_ROOT,
        captureOutput: false,
      });
      continue;
    }

    await addLiveKitProjectManually(ui, existingAgentEnv);
  }
}

function listConfiguredLiveKitProjects(): {
  projects: LiveKitProject[];
  detail: string;
} {
  try {
    const payload = runJsonCommand(['lk', 'project', 'list', '-j'], { cwd: REPO_ROOT });
    if (!Array.isArray(payload)) {
      return {
        projects: [],
        detail: 'The LiveKit CLI returned an unexpected project list format.',
      };
    }

    const projects = normalizeLiveKitProjects(payload);

    if (projects.length === 0) {
      return {
        projects: [],
        detail: 'No linked LiveKit projects were returned.',
      };
    }

    return { projects, detail: `${projects.length} linked project(s) found.` };
  } catch (error) {
    return {
      projects: [],
      detail: error instanceof Error ? error.message : String(error),
    };
  }
}

export function normalizeLiveKitProjects(payload: unknown): LiveKitProject[] {
  if (!Array.isArray(payload)) {
    return [];
  }

  return payload
    .map((value) => {
      const item = value as Record<string, unknown>;
      return {
        name: typeof item.Name === 'string' ? item.Name : '',
        url: typeof item.URL === 'string' ? item.URL : '',
        apiKey: typeof item.APIKey === 'string' ? item.APIKey : '',
        apiSecret: typeof item.APISecret === 'string' ? item.APISecret : '',
        projectId: typeof item.ProjectId === 'string' && item.ProjectId ? item.ProjectId : null,
      };
    })
    .filter((item) => item.name && item.url && item.apiKey && item.apiSecret);
}

async function addLiveKitProjectManually(
  ui: ReturnType<typeof createPrompter>,
  existingAgentEnv: Record<string, string>
): Promise<void> {
  note(
    'Paste the LiveKit Cloud project credentials from your dashboard. RepoLine will add them to the `lk` CLI and then reuse that linked project in setup.',
    'Manual LiveKit project'
  );
  const projectName = await ui.promptText('LiveKit project name');
  const url = await ui.promptText('LiveKit WebSocket URL', existingAgentEnv.LIVEKIT_URL);
  const apiKey = await ui.promptText('LiveKit API key', existingAgentEnv.LIVEKIT_API_KEY);
  const apiSecret = await ui.promptText('LiveKit API secret', existingAgentEnv.LIVEKIT_API_SECRET);
  runChecked(
    [
      'lk',
      'project',
      'add',
      projectName,
      '--url',
      url,
      '--api-key',
      apiKey,
      '--api-secret',
      apiSecret,
      '--default',
    ],
    {
      cwd: REPO_ROOT,
      captureOutput: true,
    }
  );
}

async function selectWorkdir(
  ui: ReturnType<typeof createPrompter>,
  existingWorkdir: string | null,
  preferredWorkdir?: string
): Promise<string> {
  if (preferredWorkdir) {
    const resolvedPreferredWorkdir = resolveHome(preferredWorkdir);
    return validateWorkdir(
      noteAndReturn(
        resolvedPreferredWorkdir,
        `Using coding CLI workdir: ${resolvedPreferredWorkdir}`,
        'Workdir'
      )
    );
  }

  const candidates = discoverRepoCandidates(existingWorkdir);
  if (candidates.length === 1) {
    return noteAndReturn(
      candidates[0],
      `Using the only detected git repo: ${candidates[0]}`,
      'Workdir'
    );
  }

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
      try {
        return validateWorkdir(resolveHome(value));
      } catch (error) {
        note(error instanceof Error ? error.message : String(error), 'Try again');
      }
    }
  }

  return candidates[selection];
}

function validateWorkdir(pathValue: string): string {
  if (!isDirectory(pathValue)) {
    throw new BridgeCliError(`Path does not exist: ${pathValue}`);
  }
  if (!existsSync(join(pathValue, '.git'))) {
    throw new BridgeCliError(`Path is not a git repo: ${pathValue}`);
  }
  return pathValue;
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
  const availableNumbers = await ensureProjectPhoneNumbers(ui, project, projectNumbers);
  const phoneNumber = await choosePhoneNumber(ui, availableNumbers, existingPhone?.number ?? null);
  const pin = await promptPin(ui, existingPhone?.pin ?? null);
  const dispatchRuleName = slugify(`${agentName}-inbound`);
  const existingDispatch = selectDispatchRule(project.name, dispatchRuleName);

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
    trunkIds: [phoneNumber.id],
    ...(existingDispatch?.inboundNumbers?.length
      ? { inboundNumbers: existingDispatch.inboundNumbers }
      : {}),
  };

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
    number: phoneNumber.e164Format,
    pin,
    dispatchRuleName,
    dispatchRuleId: dispatch.sipDispatchRuleId,
  };
}

async function ensureProjectPhoneNumbers(
  ui: ReturnType<typeof createPrompter>,
  project: LiveKitProject,
  existingNumbers: PhoneNumberRecord[]
): Promise<PhoneNumberRecord[]> {
  if (existingNumbers.length > 0) {
    return existingNumbers;
  }

  note(
    [
      `No active LiveKit phone numbers were found for ${project.name}.`,
      `As of ${LIVEKIT_PHONE_NUMBER_GUIDANCE_DATE}, LiveKit Cloud plans include 1 free US local number, but you still have to search for it and purchase or assign it before inbound calls will work.`,
      'RepoLine can do that from the CLI now and then attach the new number to a dispatch rule.',
    ].join('\n'),
    'Phone number required'
  );

  const shouldSearch = await ui.promptBool('Search LiveKit for a US local phone number now?', true);
  if (!shouldSearch) {
    throw new BridgeCliError(
      'phone setup requires an active LiveKit phone number. Rerun setup when you are ready to add one.'
    );
  }

  while (true) {
    const preferredAreaCode = await ui.promptOptionalText(
      'Preferred US area code (optional, for example 415 or 484)'
    );
    const numbers = searchAvailablePhoneNumbers(project.name, preferredAreaCode || null);
    if (numbers.length === 0) {
      const detail = preferredAreaCode
        ? `No purchasable numbers were returned for area code ${preferredAreaCode}.`
        : 'No purchasable US local numbers were returned.';
      note(`${detail}\nTry a different area code or retry without one.`, 'No numbers found');
      const shouldRetry = await ui.promptBool('Search again?', true);
      if (!shouldRetry) {
        throw new BridgeCliError(
          'phone setup requires an active LiveKit phone number. Rerun setup when you are ready to add one.'
        );
      }
      continue;
    }

    const selection = await ui.selectOption(
      'Choose the LiveKit phone number to purchase',
      numbers.map((item) => ({
        label: item.e164Format,
        hint: formatSearchablePhoneNumber(item),
      })),
      0
    );
    const numberToPurchase = numbers[selection];

    note(
      [
        `LiveKit docs say that, as of ${LIVEKIT_PHONE_NUMBER_GUIDANCE_DATE}, Cloud plans include 1 free US local phone number.`,
        'Additional numbers or usage can still incur charges, so RepoLine will only continue if you confirm the purchase.',
      ].join('\n'),
      'Billing'
    );
    const shouldPurchase = await ui.promptBool(
      `Purchase ${numberToPurchase.e164Format} in LiveKit now?`,
      true
    );
    if (!shouldPurchase) {
      const shouldRetry = await ui.promptBool('Search for a different phone number instead?', true);
      if (!shouldRetry) {
        throw new BridgeCliError(
          'phone setup requires an active LiveKit phone number. Rerun setup when you are ready to add one.'
        );
      }
      continue;
    }

    purchasePhoneNumber(project.name, numberToPurchase.e164Format);
    const refreshedNumbers = listPhoneNumbers(project.name);
    if (refreshedNumbers.length > 0) {
      return refreshedNumbers;
    }

    throw new BridgeCliError('LiveKit reported a successful purchase, but no active phone numbers were found.');
  }
}

async function choosePhoneNumber(
  ui: ReturnType<typeof createPrompter>,
  numbers: PhoneNumberRecord[],
  existingNumber: string | null
): Promise<PhoneNumberRecord> {
  if (numbers.length === 0) {
    throw new BridgeCliError(
      'no active phone number was found for this LiveKit project. Let setup search for one, or add one in LiveKit first and rerun setup.'
    );
  }

  if (numbers.length === 1) {
    note(`Using the only active project number: ${numbers[0].e164Format}`, 'Phone number');
    return numbers[0];
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
  return numbers[selection];
}

function searchAvailablePhoneNumbers(
  projectName: string,
  areaCode: string | null
): SearchablePhoneNumberRecord[] {
  const cmd = [
    'lk',
    '--project',
    projectName,
    'number',
    'search',
    '--country-code',
    'US',
    '--limit',
    '12',
    ...(areaCode ? ['--area-code', areaCode] : []),
  ];

  try {
    const payload = runJsonCommand([...cmd, '--json'], {
      cwd: REPO_ROOT,
    });
    const records = normalizeSearchablePhoneNumbers(payload);
    if (records.length > 0) {
      return records;
    }
  } catch {}

  const output = runChecked(cmd, {
    cwd: REPO_ROOT,
    captureOutput: true,
  }).stdout;
  return parseSearchablePhoneNumbersTable(output);
}

function purchasePhoneNumber(projectName: string, phoneNumber: string): void {
  runChecked(
    ['lk', '--project', projectName, '--yes', 'number', 'purchase', '--numbers', phoneNumber],
    {
      cwd: REPO_ROOT,
      captureOutput: true,
    }
  );
}

function listPhoneNumbers(projectName: string): PhoneNumberRecord[] {
  const payload = runJsonCommand(['lk', '--project', projectName, 'number', 'list', '-j'], {
    cwd: REPO_ROOT,
  }) as { items?: PhoneNumberRecord[] };
  const items = payload.items ?? [];
  return items.filter(
    (item) =>
      item.status === PHONE_NUMBER_STATUS_ACTIVE &&
      typeof item.id === 'string' &&
      typeof item.e164Format === 'string'
  );
}

export function normalizeSearchablePhoneNumbers(payload: unknown): SearchablePhoneNumberRecord[] {
  const records = Array.isArray(payload)
    ? payload
    : payload && typeof payload === 'object' && Array.isArray((payload as { items?: unknown[] }).items)
      ? (payload as { items: unknown[] }).items
      : [];
  return records
    .map((item) => normalizeSearchablePhoneNumber(item))
    .filter((item): item is SearchablePhoneNumberRecord => item !== null);
}

export function normalizeSearchablePhoneNumber(value: unknown): SearchablePhoneNumberRecord | null {
  if (!value || typeof value !== 'object') {
    return null;
  }
  const item = value as Record<string, unknown>;
  const e164Format = readStringValue(
    item.e164Format,
    item.e164,
    item.number,
    item.Number,
    item.E164
  );
  if (!e164Format) {
    return null;
  }
  return {
    e164Format,
    countryCode: readStringValue(item.countryCode, item.Country),
    areaCode: readStringValue(item.areaCode, item['Area Code']),
    locality: readStringValue(item.locality, item.Locality),
    region: readStringValue(item.region, item.Region),
  };
}

export function parseSearchablePhoneNumbersTable(output: string): SearchablePhoneNumberRecord[] {
  const rowValues = output
    .split('\n')
    .map((line) => line.trim())
    .filter((line) => line.startsWith('│') && line.endsWith('│'))
    .map((line) =>
      line
        .slice(1, -1)
        .split('│')
        .map((part) => part.trim())
    );

  if (rowValues.length <= 1) {
    return [];
  }

  const header = rowValues[0];
  const e164Index = header.indexOf('E164');
  if (e164Index < 0) {
    return [];
  }

  const areaCodeIndex = header.indexOf('Area Code');
  const countryIndex = header.indexOf('Country');
  const localityIndex = header.indexOf('Locality');
  const regionIndex = header.indexOf('Region');

  return rowValues
    .slice(1)
    .map((row) => ({
      e164Format: row[e164Index] ?? '',
      areaCode: areaCodeIndex >= 0 ? row[areaCodeIndex] : undefined,
      countryCode: countryIndex >= 0 ? row[countryIndex] : undefined,
      locality: localityIndex >= 0 ? row[localityIndex] : undefined,
      region: regionIndex >= 0 ? row[regionIndex] : undefined,
    }))
    .filter((row) => row.e164Format.length > 0);
}

function readStringValue(...values: unknown[]): string | undefined {
  for (const value of values) {
    if (typeof value === 'string' && value.trim()) {
      return value.trim();
    }
  }
  return undefined;
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
  refreshKnownPathEntries();
  const missing = tools.filter((tool) => !Bun.which(tool));
  if (missing.length > 0) {
    throw new BridgeCliError(`missing required tools: ${missing.join(', ')}`);
  }
}

async function ensureToolsAvailable(
  ui: ReturnType<typeof createPrompter>,
  tools: string[],
  label: string
): Promise<void> {
  refreshKnownPathEntries();
  const missing = tools.filter((tool) => !Bun.which(tool));
  if (missing.length === 0) {
    return;
  }

  const detailLines = missing.map(
    (tool) => `- ${tool}: ${commandInstallHint(tool) ?? 'install it manually'}`
  );
  note(
    `${label} needs a few local commands before setup can continue.\n${detailLines.join('\n')}`,
    'Missing tools'
  );

  const shouldInstall = await ui.promptBool(
    `Run ./scripts/bootstrap.sh for ${missing.join(', ')} now?`,
    true
  );
  if (!shouldInstall) {
    throw new BridgeCliError(`missing required tools: ${missing.join(', ')}`);
  }

  runBootstrapInstaller(missing);
  refreshKnownPathEntries();

  const stillMissing = tools.filter((tool) => !Bun.which(tool));
  if (stillMissing.length > 0) {
    throw new BridgeCliError(
      `bootstrap finished, but these commands are still missing: ${stillMissing.join(', ')}`
    );
  }
}

function runBootstrapInstaller(tools: string[]): void {
  runChecked(['bash', BOOTSTRAP_SCRIPT_PATH, ...tools.map(bootstrapInstallTarget)], {
    cwd: REPO_ROOT,
    captureOutput: false,
  });
}

function bootstrapInstallTarget(tool: string): string {
  if (tool === 'cursor-agent') {
    return 'cursor';
  }
  return tool;
}

function refreshKnownPathEntries(): void {
  const candidates = [
    join(process.env.HOME ?? '', '.bun', 'bin'),
    join(process.env.HOME ?? '', '.local', 'bin'),
    '/opt/homebrew/bin',
    '/usr/local/bin',
  ];
  const currentEntries = (process.env.PATH ?? '').split(':').filter(Boolean);
  for (const candidate of candidates) {
    if (!candidate || !existsSync(candidate) || currentEntries.includes(candidate)) {
      continue;
    }
    currentEntries.unshift(candidate);
  }
  process.env.PATH = currentEntries.join(':');
}

function resolveFrontendHost(): string {
  const value = process.env.REPOLINE_FRONTEND_HOST?.trim();
  return value || DEFAULT_FRONTEND_HOST;
}

function isRemoteFrontendHost(host: string): boolean {
  const normalized = host.trim().toLowerCase();
  return normalized !== '127.0.0.1' && normalized !== 'localhost' && normalized !== '::1';
}

function assertSafeRuntimeConfig(agentEnv: Record<string, string>, frontendHost: string): void {
  const accessPolicy = (agentEnv.BRIDGE_ACCESS_POLICY ?? 'readonly').trim().toLowerCase();
  const allowOwner =
    (agentEnv.REPOLINE_ALLOW_OWNER ?? process.env.REPOLINE_ALLOW_OWNER ?? '').trim() === '1';

  if (accessPolicy === 'owner' && !allowOwner) {
    throw new BridgeCliError(
      'BRIDGE_ACCESS_POLICY=owner is blocked by default. Change it to readonly or workspace-write, or set REPOLINE_ALLOW_OWNER=1 for an explicit override.'
    );
  }

  if (
    isRemoteFrontendHost(frontendHost) &&
    process.env.REPOLINE_ALLOW_REMOTE_BROWSER !== '1'
  ) {
    throw new BridgeCliError(
      `remote browser binding to ${frontendHost} is blocked by default. Use REPOLINE_FRONTEND_HOST=127.0.0.1, or set REPOLINE_ALLOW_REMOTE_BROWSER=1 for an explicit override.`
    );
  }
}

async function selectBridgeProvider(
  ui: ReturnType<typeof createPrompter>,
  agentEnv: Record<string, string>,
  existingState: SetupState | null,
  preferredProvider?: BridgeProvider
): Promise<BridgeProvider> {
  if (preferredProvider) {
    return noteAndReturn(
      preferredProvider,
      `Using coding CLI: ${formatBridgeProvider(preferredProvider)}`,
      'Coding CLI'
    );
  }

  const provider = normalizeBridgeProvider(
    agentEnv.BRIDGE_CLI_PROVIDER ?? existingState?.bridge_provider ?? 'claude'
  );
  const installedProviders = (['claude', 'codex', 'cursor'] as const).filter((candidate) =>
    Boolean(Bun.which(providerExecutable(candidate)))
  );
  if (!agentEnv.BRIDGE_CLI_PROVIDER && !existingState?.bridge_provider && installedProviders.length === 1) {
    return noteAndReturn(
      installedProviders[0],
      `Detected a single installed coding CLI: ${formatBridgeProvider(installedProviders[0])}`,
      'Coding CLI'
    );
  }
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

export function formatSearchablePhoneNumber(number: SearchablePhoneNumberRecord): string {
  const locality = number.locality?.trim();
  const region = number.region?.trim();
  const locationParts =
    locality && region && locality.toLowerCase().endsWith(` ${region.toLowerCase()}`)
      ? [locality]
      : [locality, region];
  const location = locationParts.filter(Boolean).join(', ');
  const areaCode = number.areaCode ? `area code ${number.areaCode}` : null;
  return [location, areaCode].filter(Boolean).join(' - ') || number.e164Format;
}

function emphasize(value: string): string {
  return `\x1b[1m\x1b[36m${value}\x1b[0m`;
}

function noteAndReturn<T>(value: T, message: string, title: string): T {
  note(message, title);
  return value;
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

    async promptOptionalText(prompt: string, defaultValue?: string): Promise<string> {
      const answer = await clackText({
        message: prompt,
        placeholder: defaultValue,
        defaultValue,
      });

      if (isCancel(answer)) {
        return requirePromptValue(answer);
      }
      return typeof answer === 'string' ? answer.trim() : '';
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
      if (options.length === 1) {
        const normalized =
          typeof options[0] === 'string'
            ? { label: options[0], hint: undefined }
            : options[0];
        note(
          [normalized.label, normalized.hint].filter(Boolean).join('\n'),
          `${prompt} (auto-selected)`
        );
        return 0;
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
