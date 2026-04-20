import { expect, test } from 'bun:test';
import { spawnSync } from 'node:child_process';
import { chmodSync, cpSync, existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  loadEnvFile,
  loadSetupState,
  REPOLINE_SKILL_NAME,
  REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
  saveSetupState,
  writeEnvFile,
} from './bridge-runtime-config';
import {
  formatSearchablePhoneNumber,
  normalizeLiveKitProjects,
  normalizeSearchablePhoneNumber,
  normalizeSearchablePhoneNumbers,
  parseCliArgs,
  parseSearchablePhoneNumbersTable,
} from './phone-bridge';

const SCRIPT_DIR = dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = resolve(SCRIPT_DIR, '..');

test('parseCliArgs defaults non-setup commands to normal execution', () => {
  expect(parseCliArgs(['doctor'])).toEqual({
    command: 'doctor',
    setupOptions: {},
  });
  expect(parseCliArgs(['unknown-command'])).toEqual({
    command: null,
    setupOptions: {},
  });
});

test('parseCliArgs parses non-interactive setup flags', () => {
  expect(
    parseCliArgs([
      'setup',
      '--provider',
      'gemini',
      '--project',
      'demo',
      '--workdir',
      '/tmp/demo',
      '--agent-name',
      'smoke-agent',
      '--skip-phone',
    ])
  ).toEqual({
    command: 'setup',
    setupOptions: {
      bridgeProvider: 'gemini',
      livekitProjectName: 'demo',
      workdir: '/tmp/demo',
      agentName: 'smoke-agent',
      setupPhone: false,
    },
  });
});

test('parseCliArgs parses setup preset and phone-only flags', () => {
  expect(
    parseCliArgs([
      'setup',
      '--preset',
      'codex-browser',
      '--phone-only',
      '--pin',
      '2468',
    ])
  ).toEqual({
    command: 'setup',
    setupOptions: {
      preset: 'codex-browser',
      phoneOnly: true,
      setupPhone: true,
      phonePin: '2468',
    },
  });
});

test('parseCliArgs rejects unknown setup flags', () => {
  expect(() => parseCliArgs(['setup', '--wat'])).toThrow('unknown setup option');
  expect(() => parseCliArgs(['setup', '--provider'])).toThrow('--provider requires a value');
  expect(() => parseCliArgs(['setup', '--preset', 'wat'])).toThrow('unsupported --preset value');
  expect(() => parseCliArgs(['setup', '--pin', '12'])).toThrow('--pin requires exactly 4 digits');
});

test('normalizeLiveKitProjects keeps only complete project records', () => {
  expect(
    normalizeLiveKitProjects([
      {
        Name: 'demo',
        URL: 'wss://demo.livekit.cloud',
        APIKey: 'key',
        APISecret: 'secret',
        ProjectId: 'p_123',
      },
      {
        Name: 'missing-secret',
        URL: 'wss://demo.livekit.cloud',
        APIKey: 'key',
      },
    ])
  ).toEqual([
    {
      name: 'demo',
      url: 'wss://demo.livekit.cloud',
      apiKey: 'key',
      apiSecret: 'secret',
      projectId: 'p_123',
    },
  ]);
});

test('normalizeSearchablePhoneNumber handles CLI JSON shapes', () => {
  expect(
    normalizeSearchablePhoneNumber({
      e164Format: '+14845550123',
      countryCode: 'US',
      areaCode: '484',
      locality: 'PHILADELPHIA',
      region: 'PA',
    })
  ).toEqual({
    e164Format: '+14845550123',
    countryCode: 'US',
    areaCode: '484',
    locality: 'PHILADELPHIA',
    region: 'PA',
  });

  expect(
    normalizeSearchablePhoneNumber({
      E164: '+14155550123',
      Country: 'USA',
      'Area Code': '415',
      Locality: 'SAN FRANCISCO',
      Region: 'CA',
    })
  ).toEqual({
    e164Format: '+14155550123',
    countryCode: 'USA',
    areaCode: '415',
    locality: 'SAN FRANCISCO',
    region: 'CA',
  });
});

test('normalizeSearchablePhoneNumbers accepts array and items payloads', () => {
  const expected = [
    {
      e164Format: '+14845550123',
      countryCode: 'US',
      areaCode: '484',
      locality: 'PHILADELPHIA',
      region: 'PA',
    },
  ];

  expect(
    normalizeSearchablePhoneNumbers([
      {
        e164Format: '+14845550123',
        countryCode: 'US',
        areaCode: '484',
        locality: 'PHILADELPHIA',
        region: 'PA',
      },
    ])
  ).toEqual(expected);

  expect(
    normalizeSearchablePhoneNumbers({
      items: [
        {
          e164Format: '+14845550123',
          countryCode: 'US',
          areaCode: '484',
          locality: 'PHILADELPHIA',
          region: 'PA',
        },
      ],
    })
  ).toEqual(expected);
});

test('parseSearchablePhoneNumbersTable parses lk table output', () => {
  const output = `Using project [clawdbot-voice]
┌──────────────┬─────────┬───────────┬───────┬─────────────────┬────────┬──────────────┐
│ E164         │ Country │ Area Code │ Type  │ Locality        │ Region │ Capabilities │
├──────────────┼─────────┼───────────┼───────┼─────────────────┼────────┼──────────────┤
│ +14845181439 │ USA     │ 484       │ LOCAL │ PHILADELPHIA PA │ PA     │ voice        │
│ +14844818342 │ USA     │ 484       │ LOCAL │ W CHESTER       │ PA     │ voice        │
└──────────────┴─────────┴───────────┴───────┴─────────────────┴────────┴──────────────┘`;

  expect(parseSearchablePhoneNumbersTable(output)).toEqual([
    {
      e164Format: '+14845181439',
      countryCode: 'USA',
      areaCode: '484',
      locality: 'PHILADELPHIA PA',
      region: 'PA',
    },
    {
      e164Format: '+14844818342',
      countryCode: 'USA',
      areaCode: '484',
      locality: 'W CHESTER',
      region: 'PA',
    },
  ]);
});

test('formatSearchablePhoneNumber creates readable prompt text', () => {
  expect(
    formatSearchablePhoneNumber({
      e164Format: '+14845181439',
      locality: 'PHILADELPHIA PA',
      region: 'PA',
      areaCode: '484',
    })
  ).toBe('PHILADELPHIA PA - area code 484');
});

test('setup smoke test runs non-interactively with stub CLIs', () => {
  const fixtureDir = mkdtempSync(join(tmpdir(), 'phone-bridge-setup-'));

  try {
    const repoRoot = createSetupFixture(fixtureDir);
    const workdir = join(repoRoot, 'workdir');
    const fakeBinDir = join(repoRoot, 'fake-bin');
    const commandLogPath = join(repoRoot, 'commands.log');
    const fakeHomeDir = join(repoRoot, 'home');

    mkdirSync(join(workdir, '.git'), { recursive: true });
    mkdirSync(fakeBinDir, { recursive: true });
    mkdirSync(join(fakeHomeDir, '.gemini'), { recursive: true });
    writeFileSync(join(fakeHomeDir, '.gemini', 'oauth_creds.json'), '{"token":"test"}\n');
    writeFakeExecutables(fakeBinDir, commandLogPath);

    const result = spawnSync(
      process.execPath,
      [
        'run',
        join(repoRoot, 'scripts', 'phone-bridge.ts'),
        'setup',
        '--provider',
        'gemini',
        '--project',
        'demo',
        '--workdir',
        workdir,
        '--agent-name',
        'smoke-agent',
        '--skip-phone',
      ],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          HOME: fakeHomeDir,
          PATH: `${fakeBinDir}:${process.env.PATH ?? ''}`,
          REPOLINE_TEST_COMMAND_LOG: commandLogPath,
        },
        encoding: 'utf8',
      }
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain(
      'Setup complete. Run `bun run live` when you are ready to start RepoLine.'
    );

    const agentEnv = loadEnvFile(join(repoRoot, 'agent', '.env.local'));
    const frontendEnv = loadEnvFile(join(repoRoot, 'frontend', '.env.local'));
    const state = loadSetupState(join(repoRoot, '.bridge', 'state.json'));

    expect(agentEnv.LIVEKIT_URL).toBe('wss://demo.livekit.cloud');
    expect(agentEnv.BRIDGE_CLI_PROVIDER).toBe('gemini');
    expect(agentEnv.BRIDGE_WORKDIR).toBe(workdir);
    expect(agentEnv.LIVEKIT_AGENT_NAME).toBe('smoke-agent');
    expect(frontendEnv.AGENT_NAME).toBe('smoke-agent');
    expect(state).toMatchObject({
      livekit_project_name: 'demo',
      livekit_url: 'wss://demo.livekit.cloud',
      bridge_provider: 'gemini',
      workdir,
      agent_name: 'smoke-agent',
      phone: null,
    });

    expect(
      existsSync(
        join(workdir, '.agents', 'skills', REPOLINE_SKILL_NAME, 'SKILL.md')
      )
    ).toBe(true);
    expect(
      existsSync(
        join(
          workdir,
          '.agents',
          'skills',
          REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
          'references',
          'PROVIDER_NOTES.md'
        )
      )
    ).toBe(true);

    const commandLog = readFileSync(commandLogPath, 'utf8');
    expect(commandLog).toContain('lk project list -j');
    expect(commandLog).toContain('lk --project demo number list -j');
    expect(commandLog).toContain('uv sync');
    expect(commandLog).toContain('uv run python src/agent.py download-files');
    expect(commandLog).toContain('bun install');
  } finally {
    rmSync(fixtureDir, { recursive: true, force: true });
  }
});

test('phone-only setup reuses existing runtime config and wires dispatch quickly', () => {
  const fixtureDir = mkdtempSync(join(tmpdir(), 'phone-bridge-phone-only-'));

  try {
    const repoRoot = createSetupFixture(fixtureDir);
    const workdir = join(repoRoot, 'workdir');
    const fakeBinDir = join(repoRoot, 'fake-bin');
    const commandLogPath = join(repoRoot, 'commands.log');

    mkdirSync(join(workdir, '.git'), { recursive: true });
    mkdirSync(fakeBinDir, { recursive: true });
    writePhoneOnlyFakeExecutables(fakeBinDir, commandLogPath);

    writeEnvFile(join(repoRoot, 'agent', '.env.local'), {
      LIVEKIT_URL: 'wss://demo.livekit.cloud',
      LIVEKIT_API_KEY: 'lk_key',
      LIVEKIT_API_SECRET: 'lk_secret',
      LIVEKIT_AGENT_NAME: 'smoke-agent',
      BRIDGE_CLI_PROVIDER: 'codex',
      BRIDGE_WORKDIR: workdir,
      REPOLINE_SKILL_NAME,
      REPOLINE_TTS_PRONUNCIATION_SKILL_NAME,
    });
    writeEnvFile(join(repoRoot, 'frontend', '.env.local'), {
      LIVEKIT_API_KEY: 'lk_key',
      LIVEKIT_API_SECRET: 'lk_secret',
      LIVEKIT_URL: 'wss://demo.livekit.cloud',
      AGENT_NAME: 'smoke-agent',
      NEXT_PUBLIC_APP_URL: 'http://localhost:3000',
    });
    saveSetupState(join(repoRoot, '.bridge', 'state.json'), {
      configured_at: '2026-04-20T00:00:00.000Z',
      livekit_project_name: 'demo',
      livekit_url: 'wss://demo.livekit.cloud',
      bridge_provider: 'codex',
      workdir,
      agent_name: 'smoke-agent',
      phone: null,
    });

    const result = spawnSync(
      process.execPath,
      [
        'run',
        join(repoRoot, 'scripts', 'phone-bridge.ts'),
        'setup',
        '--phone-only',
        '--pin',
        '2468',
      ],
      {
        cwd: repoRoot,
        env: {
          ...process.env,
          PATH: `${fakeBinDir}:${process.env.PATH ?? ''}`,
          REPOLINE_TEST_COMMAND_LOG: commandLogPath,
        },
        encoding: 'utf8',
      }
    );

    expect(result.status).toBe(0);
    expect(result.stdout).toContain('Phone setup complete.');

    const state = loadSetupState(join(repoRoot, '.bridge', 'state.json'));
    expect(state?.phone).toEqual({
      number: '+14845550123',
      pin: '2468',
      dispatchRuleName: 'smoke-agent-inbound',
      dispatchRuleId: 'rule_123',
    });

    const commandLog = readFileSync(commandLogPath, 'utf8');
    expect(commandLog).toContain('lk project list -j');
    expect(commandLog).toContain('lk --project demo number list -j');
    expect(commandLog).toContain('lk --project demo sip dispatch list -j');
    expect(commandLog).toContain('lk --project demo sip dispatch update --id rule_123 -');
  } finally {
    rmSync(fixtureDir, { recursive: true, force: true });
  }
});

function createSetupFixture(root: string): string {
  const repoRoot = join(root, 'fixture');
  mkdirSync(repoRoot, { recursive: true });
  mkdirSync(join(repoRoot, 'scripts'), { recursive: true });
  mkdirSync(join(repoRoot, 'agent'), { recursive: true });
  mkdirSync(join(repoRoot, 'frontend'), { recursive: true });
  mkdirSync(join(repoRoot, 'skills'), { recursive: true });

  cpSync(join(REPO_ROOT, 'scripts', 'phone-bridge.ts'), join(repoRoot, 'scripts', 'phone-bridge.ts'));
  cpSync(
    join(REPO_ROOT, 'scripts', 'bridge-runtime-config.ts'),
    join(repoRoot, 'scripts', 'bridge-runtime-config.ts')
  );
  cpSync(
    join(REPO_ROOT, 'scripts', 'bridge-installation-contract.ts'),
    join(repoRoot, 'scripts', 'bridge-installation-contract.ts')
  );
  cpSync(join(REPO_ROOT, 'scripts', 'bridge-doctor.ts'), join(repoRoot, 'scripts', 'bridge-doctor.ts'));
  cpSync(join(REPO_ROOT, 'skills', REPOLINE_SKILL_NAME), join(repoRoot, 'skills', REPOLINE_SKILL_NAME), {
    recursive: true,
  });
  cpSync(
    join(REPO_ROOT, 'skills', REPOLINE_TTS_PRONUNCIATION_SKILL_NAME),
    join(repoRoot, 'skills', REPOLINE_TTS_PRONUNCIATION_SKILL_NAME),
    {
      recursive: true,
    }
  );

  return repoRoot;
}

function writeFakeExecutables(fakeBinDir: string, commandLogPath: string): void {
  writeExecutable(
    join(fakeBinDir, 'lk'),
    `#!/bin/sh
printf '%s\n' "lk $*" >> "$REPOLINE_TEST_COMMAND_LOG"
if [ "$1" = "project" ] && [ "$2" = "list" ] && [ "$3" = "-j" ]; then
  printf '%s\n' '[{"Name":"demo","URL":"wss://demo.livekit.cloud","APIKey":"lk_key","APISecret":"lk_secret","ProjectId":"proj_123"}]'
  exit 0
fi
if [ "$1" = "--project" ] && [ "$2" = "demo" ] && [ "$3" = "number" ] && [ "$4" = "list" ] && [ "$5" = "-j" ]; then
  printf '%s\n' '{"items":[]}'
  exit 0
fi
printf '%s\n' "unexpected lk args: $*" >&2
exit 1
`
  );

  writeExecutable(
    join(fakeBinDir, 'uv'),
    `#!/bin/sh
printf '%s\n' "uv $*" >> "$REPOLINE_TEST_COMMAND_LOG"
exit 0
`
  );

  writeExecutable(
    join(fakeBinDir, 'bun'),
    `#!/bin/sh
printf '%s\n' "bun $*" >> "$REPOLINE_TEST_COMMAND_LOG"
if [ "$1" = "install" ]; then
  exit 0
fi
printf '%s\n' "unexpected bun args: $*" >&2
exit 1
`
  );

  writeExecutable(
    join(fakeBinDir, 'cursor-agent'),
    `#!/bin/sh
printf '%s\n' "cursor-agent $*" >> "$REPOLINE_TEST_COMMAND_LOG"
if [ "$1" = "status" ]; then
  printf '%s\n' 'Logged in'
  exit 0
fi
if [ "$1" = "login" ]; then
  exit 0
fi
printf '%s\n' "unexpected cursor-agent args: $*" >&2
exit 1
`
  );

  writeExecutable(
    join(fakeBinDir, 'gemini'),
    `#!/bin/sh
printf '%s\n' "gemini $*" >> "$REPOLINE_TEST_COMMAND_LOG"
exit 0
`
  );

  writeFileSync(commandLogPath, '');
}

function writePhoneOnlyFakeExecutables(fakeBinDir: string, commandLogPath: string): void {
  writeExecutable(
    join(fakeBinDir, 'lk'),
    `#!/bin/sh
printf '%s\n' "lk $*" >> "$REPOLINE_TEST_COMMAND_LOG"
if [ "$1" = "project" ] && [ "$2" = "list" ] && [ "$3" = "-j" ]; then
  printf '%s\n' '[{"Name":"demo","URL":"wss://demo.livekit.cloud","APIKey":"lk_key","APISecret":"lk_secret","ProjectId":"proj_123"}]'
  exit 0
fi
if [ "$1" = "--project" ] && [ "$2" = "demo" ] && [ "$3" = "number" ] && [ "$4" = "list" ] && [ "$5" = "-j" ]; then
  printf '%s\n' '{"items":[{"id":"pn_123","e164Format":"+14845550123","locality":"PHILADELPHIA","region":"PA","status":"PHONE_NUMBER_STATUS_ACTIVE"}]}'
  exit 0
fi
if [ "$1" = "--project" ] && [ "$2" = "demo" ] && [ "$3" = "sip" ] && [ "$4" = "dispatch" ] && [ "$5" = "list" ] && [ "$6" = "-j" ]; then
  printf '%s\n' '{"items":[{"name":"smoke-agent-inbound","sipDispatchRuleId":"rule_123","inboundNumbers":["+14845550123"]}]}'
  exit 0
fi
if [ "$1" = "--project" ] && [ "$2" = "demo" ] && [ "$3" = "sip" ] && [ "$4" = "dispatch" ] && [ "$5" = "update" ] && [ "$6" = "--id" ] && [ "$7" = "rule_123" ] && [ "$8" = "-" ]; then
  cat >/dev/null
  exit 0
fi
printf '%s\n' "unexpected lk args: $*" >&2
exit 1
`
  );
}

function writeExecutable(pathValue: string, contents: string): void {
  writeFileSync(pathValue, contents);
  chmodSync(pathValue, 0o755);
}
