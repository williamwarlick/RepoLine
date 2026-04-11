import { existsSync, lstatSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

import type { BridgeProvider, SetupState } from './bridge-runtime-config';

export type DoctorCheck = {
  name: string;
  ok: boolean;
  detail: string;
};

export type DispatchRuleRecord = {
  sipDispatchRuleId: string;
  name?: string;
  inboundNumbers?: string[];
  trunkIds?: string[];
};

export function projectSkillPath(provider: BridgeProvider): string[] {
  if (provider === 'codex') {
    return ['.agents', 'skills'];
  }
  if (provider === 'cursor') {
    return ['.cursor', 'rules'];
  }
  return ['.claude', 'skills'];
}

export function isRepoLineSkillDirectory(pathValue: string, skillName: string): boolean {
  const skillPath = join(pathValue, 'SKILL.md');
  if (!existsSync(skillPath)) {
    return false;
  }

  const contents = readFileSync(skillPath, 'utf8');
  return new RegExp(`(^|\\n)name:\\s*${skillName}(\\n|$)`).test(contents);
}

export function isRepoLineCursorRule(pathValue: string, skillName: string): boolean {
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

export function checkCommandAvailable(name: string): DoctorCheck {
  const pathValue = Bun.which(name);
  const installHint = commandInstallHint(name);
  return {
    name: `Command \`${name}\``,
    ok: Boolean(pathValue),
    detail: pathValue ?? (installHint ? `not found; ${installHint}` : 'not found'),
  };
}

export function commandInstallHint(name: string): string | null {
  if (name === 'lk') {
    return 'run `./scripts/bootstrap.sh lk`';
  }
  if (name === 'uv') {
    return 'run `./scripts/bootstrap.sh uv`';
  }
  if (name === 'bun') {
    return 'run `./scripts/bootstrap.sh bun`';
  }
  if (name === 'claude') {
    return 'run `./scripts/bootstrap.sh claude`';
  }
  if (name === 'codex') {
    return 'run `./scripts/bootstrap.sh codex`';
  }
  if (name === 'cursor-agent') {
    return 'run `./scripts/bootstrap.sh cursor`';
  }
  return null;
}

export function checkFileExists(name: string, pathValue: string): DoctorCheck {
  return {
    name,
    ok: existsSync(pathValue),
    detail: pathValue,
  };
}

export function checkEnvKey(
  label: string,
  env: Record<string, string>,
  key: string
): DoctorCheck {
  const value = env[key] ?? '';
  return {
    name: `${label} ${key}`,
    ok: value.length > 0,
    detail: value.length > 0 ? 'set' : 'missing',
  };
}

export function checkInstalledRepoLineSkill(
  provider: BridgeProvider | null,
  workdir: string,
  skillName: string,
  label = 'RepoLine instructions install'
): DoctorCheck {
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

  const installed =
    provider === 'cursor'
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

export function checkPhoneState(
  state: SetupState,
  resolveDispatchRule: (
    projectName: string,
    dispatchRuleName: string
  ) => DispatchRuleRecord | null,
  resolvePhoneNumberId: (
    projectName: string,
    phoneNumber: string
  ) => string | null
): DoctorCheck {
  if (!state.phone) {
    return { name: 'Phone number wiring', ok: true, detail: 'not configured' };
  }

  try {
    const dispatch = resolveDispatchRule(
      state.livekit_project_name,
      state.phone.dispatchRuleName
    );
    if (!dispatch) {
      return { name: 'Phone number wiring', ok: false, detail: 'dispatch rule not found' };
    }
    const phoneNumberId = resolvePhoneNumberId(
      state.livekit_project_name,
      state.phone.number
    );
    const matchesLegacyNumberScope = (dispatch.inboundNumbers ?? []).includes(state.phone.number);
    const matchesAssignedTrunk =
      phoneNumberId != null && (dispatch.trunkIds ?? []).includes(phoneNumberId);

    if (!matchesLegacyNumberScope && !matchesAssignedTrunk) {
      return {
        name: 'Phone number wiring',
        ok: false,
        detail: 'dispatch rule is not associated with the configured project number',
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
