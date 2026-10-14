import path from 'node:path';
import { promises as fs } from 'node:fs';
import { requireValue } from './oauth.mjs';

export const PERMISSION_PROFILE = 'kelion_siwc_readonly';
export function permissionConfiguration({ workspace, protectedPaths, platform = process.platform, codexExecutable }) {
  requireValue(path.isAbsolute(workspace) && Array.isArray(protectedPaths) && protectedPaths.length > 0 && protectedPaths.every(p => typeof p === 'string' && path.isAbsolute(p)), 'absolute_permission_paths_required');
  const root = path.resolve(workspace), denied = [...new Set(protectedPaths.map(p => path.resolve(p)))];
  // The tool workspace must be a separate empty directory, never a parent or
  // descendant of private state. Exact deny rules cannot be reopened by it.
  for (const p of denied) {
    const a = path.relative(root, p), b = path.relative(p, root);
    requireValue(a && b && (a.startsWith('..' + path.sep) || path.isAbsolute(a)) && (b.startsWith('..' + path.sep) || path.isAbsolute(b)), 'private_workspace_overlap');
  }
  if (platform === 'linux') denied.push('/proc', '/run/credentials');
  const filesystem = { ':root': 'deny', ':minimal': 'read', ':workspace_roots': { '.': 'read' } };
  // The pinned public runtime must be visible inside the otherwise restricted sandbox.
  // Never grant access to private state, the workspace, their ancestors, or root.
  if (platform === 'linux' && codexExecutable !== undefined) {
    requireValue(typeof codexExecutable === 'string' && path.isAbsolute(codexExecutable), 'absolute_codex_runtime_required');
    const runtimeDirectory = path.dirname(path.resolve(codexExecutable));
    requireValue(runtimeDirectory !== path.parse(runtimeDirectory).root, 'runtime_root_read_refused');
    for (const p of [...denied, root]) {
      const a = path.relative(runtimeDirectory, p), b = path.relative(p, runtimeDirectory);
      requireValue(a && b && (a.startsWith('..' + path.sep) || path.isAbsolute(a)) && (b.startsWith('..' + path.sep) || path.isAbsolute(b)), 'runtime_private_workspace_overlap');
    }
    filesystem[runtimeDirectory] = 'read';
  }
  for (const p of denied.sort()) filesystem[p] = 'deny';
  return { default_permissions: PERMISSION_PROFILE, permissions: { [PERMISSION_PROFILE]: { filesystem, network: { enabled: false } } } };
}
const toml = value => {
  if (value && typeof value === 'object') return '{' + Object.entries(value).map(([k,v]) => JSON.stringify(k) + '=' + toml(v)).join(',') + '}';
  return JSON.stringify(value);
};
export function permissionArgs(configuration) {
  requireValue(configuration?.default_permissions === PERMISSION_PROFILE, 'named_permission_profile_required');
  return ['-c', 'default_permissions=' + JSON.stringify(PERMISSION_PROFILE), '-c', 'permissions.' + PERMISSION_PROFILE + '=' + toml(configuration.permissions[PERMISSION_PROFILE])];
}
export async function assertEmptyWorkspace(workspace) {
  const stat = await fs.lstat(workspace);
  requireValue(stat.isDirectory() && !stat.isSymbolicLink() && (await fs.readdir(workspace)).length === 0, 'separate_empty_workspace_required');
  requireValue(path.resolve(await fs.realpath(workspace)) === path.resolve(workspace), 'canonical_workspace_required');
}
