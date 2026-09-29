#!/usr/bin/env bash
set -euo pipefail

cd "$(git rev-parse --show-toplevel)"

if [[ "$(git branch --show-current)" != "manual/t107-blocking-core" ]]; then
  echo "ERROR: expected manual/t107-blocking-core" >&2
  exit 1
fi

PY=.venv/bin/python
if [[ ! -x "$PY" ]]; then
  PY=python3
fi

export PYTHONPATH="$PWD${PYTHONPATH:+:$PYTHONPATH}"

tracked_targets=(
  forge_backend.py
  forge_migrations.py
  forge_routes/owned_social.py
  forge_routes/owned_social_http.py
  static/forge_demo.html
  tests/owned_social_frontend.cjs
  tests/test_owned_social_models.py
  tests/test_migration_tooling.py
  tests/test_database_bootstrap.py
  tests/_v2_contract.py
)

echo "Resetting only prior helper-owned partial edits..."
git restore --source=HEAD --worktree -- "${tracked_targets[@]}"

for generated in \
  migrations/r20260929_03_blocking_core.py \
  migrations/20260929_03_blocking_core.json \
  tests/test_blocking_core_service.py \
  tests/test_blocking_core_migration.py
do
  if [[ -e "$generated" ]] && git status --porcelain -- "$generated" | grep -q '^?? '; then
    echo "Removing interrupted generated artifact: $generated"
    rm -f -- "$generated"
  fi
done

TMP_HELPER="$(mktemp -t forge-t107-helper.XXXXXX.py)"
trap 'rm -f -- "$TMP_HELPER"' EXIT

"$PY" - "$TMP_HELPER" <<'PY'
from pathlib import Path
import sys

source = Path("scripts/t107_apply_backend.py").read_text()
old = '''src = replace_once(
    src,
    """    assert verified[\\"revision\\"] == owned_social.REVISION\\n""",
    """    assert verified[\\"revision\\"] == blocking.REVISION\\n""",
    "verified head assertion",
)
'''
new = '''src = replace_once(
    src,
    """    verified = verify_database(engine)\\n\\n    assert verified[\\"revision\\"] == owned_social.REVISION\\n    assert verified[\\"integrity\\"] == \\"ok\\"\\n    assert verified[\\"foreignKeyViolations\\"] == []\\n""",
    """    verified = verify_database(engine)\\n\\n    assert verified[\\"revision\\"] == blocking.REVISION\\n    assert verified[\\"integrity\\"] == \\"ok\\"\\n    assert verified[\\"foreignKeyViolations\\"] == []\\n""",
    "verified normal-upgrade head assertion",
)
'''
if source.count(old) != 1:
    raise SystemExit(
        f"temporary helper hotfix source mismatch: expected 1 block, found {source.count(old)}"
    )
Path(sys.argv[1]).write_text(source.replace(old, new, 1))
PY

echo "Using $PY"
echo "Applying T-107 blocking core..."
"$PY" "$TMP_HELPER"

"$PY" - <<'PY'
from pathlib import Path


def replace_once(path, old, new, label):
    p = Path(path)
    text = p.read_text()
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1))

# Keep the bootstrap migration count future-proof.
replace_once(
    "tests/test_database_bootstrap.py",
    '        assert conn.execute(f"SELECT count(*) FROM {migrations.LEDGER_TABLE}").fetchone()[0] == 2\n',
    '        assert conn.execute(f"SELECT count(*) FROM {migrations.LEDGER_TABLE}").fetchone()[0] == len(migrations.REVISION_ORDER)\n',
    "bootstrap ledger assertion",
)

# Caller-owned block versions are safe to project and required so an inactive
# retained block row can be re-blocked after a reload without intent replay.
replace_once(
    "forge_routes/owned_social.py",
    '''                # This projection follows ordinary public profile visibility,\n                # without privileged admin inspection or hidden fields.\n                result.append({"id": peer["id"], "name": peer["name"],\n                               "role": peer["role"], "color": peer["color"],\n                               "headline": peer["headline"],\n                               "edge_version": edge["version"] if edge else 0})\n''',
    '''                # This projection follows ordinary public profile visibility.\n                # Caller-owned block version is included only so stale re-blocks can refresh.\n                own_block = self._own_block(connection, user["id"], peer["id"])\n                result.append({"id": peer["id"], "name": peer["name"],\n                               "role": peer["role"], "color": peer["color"],\n                               "headline": peer["headline"],\n                               "edge_version": edge["version"] if edge else 0,\n                               "block_version": own_block["version"] if own_block else 0})\n''',
    "suggestion own block version",
)
replace_once(
    "forge_routes/owned_social.py",
    '''                if key is not None and edge["id"] > after.get(key, 0):\n                    sections[key].append(dict(edge))\n''',
    '''                if key is not None and edge["id"] > after.get(key, 0):\n                    item = dict(edge)\n                    peer_id = edge["user_high_id"] if edge["user_low_id"] == user["id"] else edge["user_low_id"]\n                    own_block = self._own_block(connection, user["id"], peer_id)\n                    item["block_version"] = own_block["version"] if own_block else 0\n                    sections[key].append(item)\n''',
    "network own block version",
)
replace_once(
    "forge_routes/owned_social_http.py",
    '''                item = {"id": edge["id"], "counterpartUserId": peer_id,\n                        "name": peer.name if peer else "Member", "color": peer.color if peer else "",\n                        "role": peer.role if peer else "", "direction": "outgoing" if edge["requester_id"] == user.id else "incoming",\n                        "version": edge["version"], "status": edge["state"]}\n''',
    '''                item = {"id": edge["id"], "counterpartUserId": peer_id,\n                        "name": peer.name if peer else "Member", "color": peer.color if peer else "",\n                        "role": peer.role if peer else "", "direction": "outgoing" if edge["requester_id"] == user.id else "incoming",\n                        "version": edge["version"], "status": edge["state"],\n                        "blockVersion": edge.get("block_version", 0)}\n''',
    "HTTP edge block version",
)
replace_once(
    "forge_routes/owned_social_http.py",
    '''        result["suggested"] = [{**p, "edgeVersion": p.pop("edge_version")}\n                               for p in selected]\n''',
    '''        result["suggested"] = [{**p, "edgeVersion": p.pop("edge_version"),\n                                "blockVersion": p.pop("block_version")}\n                               for p in selected]\n''',
    "HTTP suggestion block version",
)
replace_once(
    "forge_routes/owned_social_http.py",
    '''            output.append({\n                "targetUserId": row["blocked_id"],\n                "name": peer.name if peer else "Member",\n                "color": peer.color if peer else "",\n                "version": row["version"],\n            })\n''',
    '''            output.append({\n                "targetUserId": row["blocked_id"],\n                "name": peer.name if peer else "Member",\n                "version": row["version"],\n            })\n''',
    "minimal block list projection",
)

# Web/WebView state and block list loading.
replace_once(
    "static/forge_demo.html",
    '''  return {mode: null, config: null, network: null, conversations: null,\n    listCursor: null, threads: new Map(), retries: new Map(), busy: new Set(),\n    observer: null, notice: '', networkLoad: 0, listLoad: 0, historyLoads: new Map()};\n''',
    '''  return {mode: null, config: null, network: null, blocks: [], conversations: null,\n    blocksCursor: null, listCursor: null, threads: new Map(), retries: new Map(), busy: new Set(),\n    observer: null, notice: '', networkLoad: 0, blockLoad: 0, listLoad: 0, historyLoads: new Map()};\n''',
    "web block state",
)
replace_once(
    "static/forge_demo.html",
    '''function socialButton(label, handler, disabled = false) {\n  return `<button class="btn btn-ghost btn-sm" ${disabled ? 'disabled' : ''} onclick="${esc(handler)}">${esc(label)}</button>`;\n}\n''',
    '''async function loadOwnedBlocks(more = false) {\n  const owner = social, generation = csrfGeneration, serial = ++owner.blockLoad;\n  if (more && !owner.blocksCursor) return;\n  const query = new URLSearchParams({limit: '20'});\n  if (more) query.set('cursor', owner.blocksCursor);\n  const payload = await socialRequest('/api/network/blocks?' + query);\n  if (!socialCurrent(owner, generation) || serial !== owner.blockLoad) return;\n  owner.blocks = more ? mergeSocialRows(owner.blocks, payload.blocks, 'targetUserId') : payload.blocks;\n  owner.blocksCursor = payload.nextCursor || null;\n}\nfunction socialButton(label, handler, disabled = false) {\n  return `<button class="btn btn-ghost btn-sm" ${disabled ? 'disabled' : ''} onclick="${esc(handler)}">${esc(label)}</button>`;\n}\n''',
    "web block loader",
)
replace_once(
    "static/forge_demo.html",
    '''        const busy = social.busy.has('network');\n        const action = (label, verb) => socialButton(label, `ownedNetworkAction('${section}',${row.id},'${verb}',this)`, busy);\n        let controls = '';\n        if (section === 'suggested') controls = action('Connect', 'connect');\n        else if (section === 'connections') controls = action(row.endorsedByMe ? 'Remove endorsement' : 'Endorse', row.endorsedByMe ? 'unendorse' : 'endorse') +\n          action('Message', 'message') + action('Disconnect', 'disconnect');\n        else if (row.direction === 'incoming') controls = action('Accept', 'accept') + action('Ignore', 'ignore');\n        else if (row.direction === 'outgoing') controls = action('Cancel request', 'cancel');\n''',
    '''        const busy = social.busy.has('network');\n        const action = (label, verb) => socialButton(label, `ownedNetworkAction('${section}',${row.id},'${verb}',this)`, busy);\n        const targetUserId = section === 'suggested' ? row.id : row.counterpartUserId;\n        const block = socialButton('Block', `ownedBlockAction(${targetUserId},true,${row.blockVersion || 0},${section === 'connections' ? "'connection'" : "'peer'"},this)`, busy);\n        let controls = '';\n        if (section === 'suggested') controls = action('Connect', 'connect') + block;\n        else if (section === 'connections') controls = action(row.endorsedByMe ? 'Remove endorsement' : 'Endorse', row.endorsedByMe ? 'unendorse' : 'endorse') +\n          action('Message', 'message') + action('Disconnect', 'disconnect') + block;\n        else if (row.direction === 'incoming') controls = action('Accept', 'accept') + action('Ignore', 'ignore') + block;\n        else if (row.direction === 'outgoing') controls = action('Cancel request', 'cancel') + block;\n''',
    "web block controls",
)
replace_once(
    "static/forge_demo.html",
    '''      (net.nextCursors[section] ? socialButton('Load more ' + label.toLowerCase(), `ownedNetworkMore('${section}',this)`, social.busy.has('network')) : '')\n    ).join('');\n}\nasync function ownedNetworkView() { await loadOwnedNetwork(); return ownedNetworkHtml(); }\n''',
    '''      (net.nextCursors[section] ? socialButton('Load more ' + label.toLowerCase(), `ownedNetworkMore('${section}',this)`, social.busy.has('network')) : '')\n    ).join('') +\n    `<h2 class="section-title">Blocked accounts</h2>` +\n    (social.blocks.map(row => `<div class="card" style="display:flex;flex-wrap:wrap;align-items:center;gap:10px;">\n      <div style="flex:1;min-width:120px;overflow-wrap:anywhere"><strong>${esc(row.name)}</strong></div>\n      <div>${socialButton('Unblock', `ownedBlockAction(${row.targetUserId},false,${row.version},'blocked',this)`, social.busy.has('network'))}</div></div>`).join('') ||\n      '<div class="empty">No blocked accounts.</div>') +\n    (social.blocksCursor ? socialButton('Load more blocked accounts', 'ownedBlocksMore(this)', social.busy.has('network')) : '');\n}\nasync function ownedNetworkView() { await Promise.all([loadOwnedNetwork(), loadOwnedBlocks()]); return ownedNetworkHtml(); }\n''',
    "web blocked list",
)
replace_once(
    "static/forge_demo.html",
    '''async function loadOwnedConversations(more = false) {\n''',
    r'''async function ownedBlocksMore(button) {
  const owner = social, generation = csrfGeneration;
  if (owner.busy.has('network')) return;
  owner.busy.add('network');
  try { await runBusyButton(button, 'Loading…', () => loadOwnedBlocks(true)); }
  catch (e) { if (socialCurrent(owner, generation)) showSocialNotice(e); }
  finally {
    owner.busy.delete('network');
    if (socialCurrent(owner, generation) && owner.network && state.view === 'network') paintSocial(ownedNetworkHtml(), 'network');
  }
}
async function ownedBlockAction(targetUserId, desired, expectedVersion, context, button) {
  const owner = social, generation = csrfGeneration;
  if (owner.mode !== 'v2' || owner.busy.has('network')) return;
  if (desired && context === 'connection' && !confirm('Block this account? This will end the current connection.')) return;
  owner.busy.add('network'); owner.notice = '';
  try {
    await runBusyButton(button, 'Working…', async () => {
      await socialRequest('/api/network/blocks/' + targetUserId, {
        method: 'PUT', body: JSON.stringify({blocked: desired, expectedVersion})
      });
      if (socialCurrent(owner, generation)) await Promise.all([loadOwnedNetwork(), loadOwnedBlocks()]);
    });
  } catch (e) {
    if (socialCurrent(owner, generation)) {
      owner.notice = socialError(e).body.error;
      try { await Promise.all([loadOwnedNetwork(), loadOwnedBlocks()]); }
      catch (refreshError) { showSocialNotice(refreshError); }
    }
  } finally {
    owner.busy.delete('network');
    if (socialCurrent(owner, generation) && owner.network && state.view === 'network') paintSocial(ownedNetworkHtml(), 'network');
  }
}
async function loadOwnedConversations(more = false) {
''',
    "web block actions",
)

# Update frontend fixtures and coverage.
replace_once(
    "tests/owned_social_frontend.cjs",
    '''const net = () => ({requests: [{id: 1, counterpartUserId: 8, name: 'Same', direction: 'incoming', version: 3}], outgoingRequests: [{id: 2, counterpartUserId: 9, name: 'Same', direction: 'outgoing', version: 4}], suggested: [{id: 10, name: 'Peer', edgeVersion: 6}], connections: [{id: 3, counterpartUserId: 11, name: 'Peer', version: 5, endorsementVersion: 7, endorsedByMe: false, endorsements: 0}], nextCursors: {suggested: 'next'}});\n''',
    '''const net = () => ({requests: [{id: 1, counterpartUserId: 8, name: 'Same', direction: 'incoming', version: 3, blockVersion: 0}], outgoingRequests: [{id: 2, counterpartUserId: 9, name: 'Same', direction: 'outgoing', version: 4, blockVersion: 2}], suggested: [{id: 10, name: 'Peer', edgeVersion: 6, blockVersion: 4}], connections: [{id: 3, counterpartUserId: 11, name: 'Peer', version: 5, endorsementVersion: 7, endorsedByMe: false, endorsements: 0, blockVersion: 0}], nextCursors: {suggested: 'next'}});\nconst blocks = () => ({blocks: [{targetUserId: 20, name: 'Blocked Peer', version: 3}], nextCursor: null});\n''',
    "frontend fixture block versions",
)
replace_once(
    "tests/owned_social_frontend.cjs",
    '''  const context = vm.createContext({state, Headers, URLSearchParams, crypto: webcrypto,\n''',
    '''  const context = vm.createContext({state, Headers, URLSearchParams, crypto: webcrypto, confirm: () => true,\n''',
    "frontend confirm stub",
)
replace_once(
    "tests/owned_social_frontend.cjs",
    '''    respond: async url => new Response(JSON.stringify(url.startsWith('/api/network') ? net() : detail()))\n''',
    '''    respond: async url => new Response(JSON.stringify(url.startsWith('/api/network/blocks') ? blocks() : url.startsWith('/api/network') ? net() : detail()))\n''',
    "frontend blocks response",
)

p = Path("tests/owned_social_frontend.cjs")
text = p.read_text()
text += r'''

test('block/unblock uses caller-owned versions and confirms live connection', async()=>{
  const s=setup(); await s.init(); await s.run('loadOwnedNetwork()'); await s.run('loadOwnedBlocks()');
  const rendered=s.run('ownedNetworkHtml()'); assert.match(rendered,/Blocked accounts/); assert.match(rendered,/Unblock/);
  let confirmed=0; s.context.confirm=()=>{confirmed++;return true;};
  s.context.respond=async(url,opts)=>new Response(JSON.stringify(opts.method==='PUT'?{ok:true,blocked:true,version:1}:url.startsWith('/api/network/blocks')?blocks():net()));
  await s.run("ownedBlockAction(11,true,0,'connection')");
  const put=s.calls.find(c=>c.opts.method==='PUT'); assert.equal(confirmed,1); assert.deepEqual(put.body,{blocked:true,expectedVersion:0});
  s.context.respond=async(url,opts)=>new Response(JSON.stringify(opts.method==='PUT'?{ok:true,blocked:false,version:4}:url.startsWith('/api/network/blocks')?blocks():net()));
  await s.run("ownedBlockAction(20,false,3,'blocked')"); assert.deepEqual(s.calls.filter(c=>c.opts.method==='PUT').at(-1).body,{blocked:false,expectedVersion:3});
});

test('stale block refreshes caller version without replay', async()=>{
  const s=setup(); await s.init(); await s.run('loadOwnedNetwork()'); await s.run('loadOwnedBlocks()');
  s.context.respond=async(url,opts)=>{
    if(opts.method==='PUT') return new Response(JSON.stringify({error:'private'}),{status:409});
    if(url.startsWith('/api/network/blocks')) return new Response(JSON.stringify({blocks:[],nextCursor:null}));
    const n=net(); n.suggested[0].blockVersion=6; return new Response(JSON.stringify(n));
  };
  await s.run("ownedBlockAction(10,true,4,'peer')");
  assert.equal(s.calls.filter(c=>c.opts.method==='PUT').length,1); assert.equal(s.run('social.network.suggested[0].blockVersion'),6); assert.match(s.run('social.notice'),/state has changed/);
});

test('account reset clears blocks and late block results stay stale', async()=>{
  const s=setup(); await s.init(); let finish;
  s.context.respond=(url)=>url.startsWith('/api/network/blocks')?new Promise(resolve=>{finish=resolve;}):new Response(JSON.stringify(net()));
  const pending=s.run('loadOwnedBlocks()'); await new Promise(setImmediate); s.run('resetSocialState()'); finish(new Response(JSON.stringify(blocks())));
  await assert.rejects(pending,e=>e.stale===true); assert.equal(s.run('social.blocks.length'),0); assert.equal(s.run('social.blocksCursor'),null);
});
'''
p.write_text(text)

# HTTP evidence: minimal block shape and reload/re-block recovery.
p = Path("tests/_v2_contract.py")
text = p.read_text()
text = text.replace(
    "    assert own.json['blocks'][0]['targetUserId'] == b\n",
    "    assert own.json['blocks'][0]['targetUserId'] == b\n    assert set(own.json['blocks'][0]) == {'targetUserId', 'name', 'version'}\n",
    1,
)
text += r'''


def test_reblock_version_is_recoverable_after_reload(client, world):
    (a, b, c, admin), svc = world
    actor = forge.db.session.get(forge.User, a)
    svc.set_block(actor, c, True, 0)
    svc.set_block(actor, c, False, 1)
    network = client.get('/api/network', headers=auth(client, a))
    assert network.status_code == 200
    row = next(item for item in network.json['suggested'] if item['id'] == c)
    assert row['blockVersion'] == 2
    blocked = client.put(f'/api/network/blocks/{c}', json={'blocked': True, 'expectedVersion': 2}, headers=auth(client, a))
    assert blocked.status_code == 200 and blocked.json['version'] == 3
'''
p.write_text(text)

# More race/rollback/lifecycle evidence.
p = Path("tests/test_blocking_core_service.py")
text = p.read_text().replace(
    "    Conflict, NotFound, OperationUnavailable, OwnedSocialService,\n",
    "    Conflict, Forbidden, NotFound, OperationUnavailable, OwnedSocialService,\n",
    1,
)
text += r'''


def test_block_racing_request_never_leaves_pending_contact(blocking_social):
    service, (a, b, _, _) = blocking_social; gate = Barrier(3)
    def request():
        gate.wait()
        try: return service.request(a, b.id, 0)['state']
        except OperationUnavailable: return 'denied'
    def block(): gate.wait(); return service.set_block(a, b.id, True, 0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(request); two=ex.submit(block); gate.wait(); assert two.result() is True; assert one.result() in {'pending','denied'}
    edges=service.own_edges(a); assert not edges or all(edge['state']=='cancelled' for edge in edges)


def test_block_racing_conversation_creation_is_denied_or_retained_readonly(blocking_social):
    service, (a, b, _, _) = blocking_social; accepted(service,a,b); gate=Barrier(3)
    def create():
        gate.wait()
        try: return service.open_conversation(b,a.id)['public_id']
        except OperationUnavailable: return None
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(create); two=ex.submit(block); gate.wait(); slug=one.result(); assert two.result() is True
    if slug: assert service.conversation_info(b,slug)['read_only'] is True


def test_block_racing_send_allows_only_prior_commit(blocking_social):
    service, (a,b,_,_) = blocking_social; accepted(service,a,b); slug=service.open_conversation(a,b.id)['public_id']; gate=Barrier(3)
    def send():
        gate.wait()
        try: return service.send(b,slug,'raced','race-send')['seq']
        except OperationUnavailable: return None
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(send); two=ex.submit(block); gate.wait(); sent=one.result(); assert two.result() is True
    assert len(service.history(b,slug)['messages']) == (1 if sent else 0); assert service.conversation_info(b,slug)['read_only']


def test_block_racing_endorsement_leaves_no_active_projection(blocking_social):
    service,(a,b,_,_)=blocking_social; edge=accepted(service,a,b); gate=Barrier(3)
    def endorse():
        gate.wait()
        try: return service.endorse(b,edge['id'],True,0)
        except OperationUnavailable: return None
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(endorse); two=ex.submit(block); gate.wait(); one.result(); assert two.result() is True
    assert service.active_endorsements(b,edge['id']) == []


def test_block_racing_read_cursor_remains_allowed(blocking_social):
    service,(a,b,_,_)=blocking_social; accepted(service,a,b); slug=service.open_conversation(a,b.id)['public_id']; msg=service.send(a,slug,'seen','race-read'); gate=Barrier(3)
    def read(): gate.wait(); return service.mark_read(b,slug,msg['seq'])
    def block(): gate.wait(); return service.set_block(a,b.id,True,0)['active']
    with ThreadPoolExecutor(max_workers=2) as ex:
        one=ex.submit(read); two=ex.submit(block); gate.wait(); assert one.result()==msg['seq']; assert two.result() is True
    assert service.history(b,slug)['last_read_seq']==msg['seq']


def test_block_transaction_rolls_back_all_side_effects(monkeypatch, blocking_social):
    service,(a,b,_,_)=blocking_social; edge=accepted(service,a,b); endorsement=service.endorse(a,edge['id'],True,0)
    monkeypatch.setattr(service,'_block_event',lambda *args,**kwargs: (_ for _ in ()).throw(RuntimeError('injected block audit failure')))
    with pytest.raises(RuntimeError,match='injected block audit failure'): service.set_block(a,b.id,True,0)
    with service.engine.connect() as connection:
        assert connection.execute(select(service.block)).mappings().all()==[]
        stored_edge=connection.execute(select(service.edge).where(service.edge.c.id==edge['id'])).mappings().one()
        stored_endorsement=connection.execute(select(service.endorsement).where(service.endorsement.c.id==endorsement['id'])).mappings().one()
    assert stored_edge['state']=='accepted' and stored_edge['version']==2; assert stored_endorsement['revoked_at'] is None and stored_endorsement['version']==1


def test_suspension_denies_actor_but_existing_own_block_remains_manageable(blocking_social):
    service,(a,b,_,_)=blocking_social; service.set_block(a,b.id,True,0)
    with service.engine.begin() as connection: connection.execute(service.user.update().where(service.user.c.id==b.id).values(suspended=True))
    assert service.set_block(a,b.id,False,1)['active'] is False
    with service.engine.begin() as connection: connection.execute(service.user.update().where(service.user.c.id==a.id).values(suspended=True))
    with pytest.raises(Forbidden): service.set_block(a,b.id,True,2)
'''
p.write_text(text)
PY

echo
echo "Running focused T-107 / owned-social / migration tests..."
"$PY" -m pytest -q --disable-warnings \
  tests/test_blocking_core_migration.py \
  tests/test_blocking_core_service.py \
  tests/test_owned_social_models.py \
  tests/test_owned_social_service.py \
  tests/test_owned_social_http_subprocess.py \
  tests/test_migration_tooling.py \
  tests/test_database_bootstrap.py

echo
echo "Running ownership-v2 frontend unit tests..."
node --test tests/owned_social_frontend.cjs

echo
echo "Running diff check..."
git diff --check

echo
echo "Working tree:"
git status --short

echo
echo "Diff summary:"
git diff --stat

echo
echo "T-107 backend/web focused verification completed successfully."
