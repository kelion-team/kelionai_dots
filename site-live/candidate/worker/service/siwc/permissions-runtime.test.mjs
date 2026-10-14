import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { permissionConfiguration, PERMISSION_PROFILE } from './permissions.mjs';
const args={workspace:'/tmp/kelion-workspace',protectedPaths:['/tmp/kelion-private'],platform:'linux',codexExecutable:'/opt/kelion-siwc/codex-0.162.0-alpha.17.2/bin/codex'};
test('pinned runtime binary is readable while private paths and network remain denied',()=>{
 const p=permissionConfiguration(args).permissions[PERMISSION_PROFILE];
 assert.equal(p.filesystem[path.dirname(args.codexExecutable)],'read');
 assert.equal(p.filesystem[':root'],'deny');
 assert.equal(p.filesystem['/tmp/kelion-private'],'deny');
 assert.equal(p.filesystem['/proc'],'deny');
 assert.equal(p.filesystem['/run/credentials'],'deny');
 assert.equal(p.network.enabled,false);
});
test('runtime cannot expose root, private state, workspace, or their parents',()=>{
 for(const codexExecutable of ['/codex','/tmp/codex','/tmp/kelion-private/bin/codex','/tmp/kelion-workspace/bin/codex','relative/codex'])
  assert.throws(()=>permissionConfiguration({...args,codexExecutable}),{name:'Error'});
});
