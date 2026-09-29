const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const {webcrypto} = require('node:crypto');
const html = fs.readFileSync('static/forge_demo.html', 'utf8');
const helpers = html.slice(html.indexOf('let csrfToken = null;'), html.indexOf('let toastTimer = null;'));
const net = () => ({requests: [{id: 1, counterpartUserId: 8, name: 'Same', direction: 'incoming', version: 3, blockVersion: 0}], outgoingRequests: [{id: 2, counterpartUserId: 9, name: 'Same', direction: 'outgoing', version: 4, blockVersion: 2}], suggested: [{id: 10, name: 'Peer', edgeVersion: 6, blockVersion: 4}], connections: [{id: 3, counterpartUserId: 11, name: 'Peer', version: 5, endorsementVersion: 7, endorsedByMe: false, endorsements: 0, blockVersion: 0}], nextCursors: {suggested: 'next'}});
const blocks = () => ({blocks: [{targetUserId: 20, name: 'Blocked Peer', version: 3}], nextCursor: null});
const message = seq => ({sequence: seq, who: 'them', text: `message ${seq}`, createdAt: '2026-09-29T10:00:00Z'});
const detail = () => ({id: 'server-slug', name: 'Peer', messages: [message(3), message(4)], hasMore: true, nextCursor: 'older', lastSequence: 4, lastReadSequence: 0, unreadCount: 4, readOnly: false});
function setup() {
  const calls = [], elements = {'social-notice': {}, content: {setAttribute(key,value){this[key]=value;}}}, state = {user: {id: 1}, view: 'network', msgSlug: null};
  const context = vm.createContext({state, Headers, URLSearchParams, crypto: webcrypto, confirm: () => true,
    FormData: class {constructor(form) {this.form = form;} get(key) {return this.form[key];}},
    navigator: {onLine: true}, document: {visibilityState: 'visible', getElementById: id => elements[id], querySelectorAll: () => []},
    esc: v => String(v ?? '').replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;').replaceAll("'",'&#39;'), prettyRole: String,
    enhanceAccessibility: () => {}, renderApp: () => {}, toast: () => {}, socket: null,
    loadView: async () => {}, goto: v => {state.view = v;},
    runBusyButton: async (button, label, fn) => {if (button?.disabled) return; if (button) button.disabled = true; try {return await fn();} finally {if(button) button.disabled = false;}},
    renderError: e => e.body.error,
    fetch: async (url, opts) => {
      calls.push({url, opts, body: opts.body && JSON.parse(opts.body)});
      if(url === '/api/auth/csrf-token') return new Response(JSON.stringify({csrfToken: 'token'}));
      if(url === '/api/social-config') return new Response(JSON.stringify({mode: 'v2'}));
      return context.respond(url, opts);
    },
    respond: async url => new Response(JSON.stringify(url.startsWith('/api/network/blocks') ? blocks() : url.startsWith('/api/network') ? net() : detail()))
  });
  const run = code => vm.runInContext(code, context);
  run(helpers);
  return {run, calls, context, state, elements, init: async () => {await run('socialMode()');}};
}
test('v2 capability and CSRF headers, explicit configuration only', async () => {
  const s=setup(); await s.init(); await s.run('loadOwnedNetwork()');
  assert.equal(s.calls.at(-1).opts.headers.get('X-Forge-Ownership-Version'), '2');
  assert.equal(s.calls[0].url, '/api/social-config');
  await s.run("ownedNetworkAction('suggested',10,'connect')");
  const write=s.calls.find(c=>c.opts.method==='POST');
  assert.equal(write.opts.headers.get('X-CSRF-Token'),'token');
  assert.equal(write.opts.credentials,'same-origin');
});
test('incoming/outgoing controls use directions, not matching names', async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');const rendered=s.run('ownedNetworkHtml()');
  for(const text of ['Incoming requests','Outgoing requests','Accept','Ignore','Cancel request','Disconnect','Message']) assert.ok(rendered.includes(text));
});
for(const [section,id,action,body] of [
  ['suggested',10,'connect',{expectedVersion:6}], ['requests',1,'accept',{expectedVersion:3}],
  ['requests',1,'ignore',{expectedVersion:3}], ['outgoingRequests',2,'cancel',{expectedVersion:4}],
  ['connections',3,'disconnect',{expectedVersion:5}], ['connections',3,'endorse',{endorsed:true,expectedVersion:7}],
  ['connections',3,'unendorse',{endorsed:false,expectedVersion:7}]
]) test(`versioned ${action}`,async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');await s.run(`ownedNetworkAction('${section}',${id},'${action}')`);
  assert.deepEqual(s.calls.find(c=>c.opts.method==='POST').body, body);
});
test('409 refreshes versions without replay', async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');
  s.context.respond=async (url,opts)=>new Response(JSON.stringify(opts.method==='POST'? {error:'private'}: net()),{status:opts.method==='POST'?409:200});
  await s.run("ownedNetworkAction('requests',1,'accept')");
  assert.equal(s.calls.filter(c=>c.opts.method==='POST').length,1);
  assert.match(s.run('social.notice'),/state has changed/);
  assert.ok(s.run('social.network'));
});
test('network cursors are section-specific and pages deduplicate',async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');
  s.context.respond=async()=>{const n=net();n.suggested.push({id:12,name:'Next',edgeVersion:0});n.nextCursors={};n.requests=[];return new Response(JSON.stringify(n));};
  await s.run("loadOwnedNetwork('suggested')");
  assert.match(s.calls.at(-1).url,/suggestedCursor=next/);
  assert.equal(s.run('social.network.suggested.length'),2);
  assert.equal(s.run('social.network.requests.length'),1);
  assert.equal(s.run('social.network.nextCursors.suggested'),null);
});
for(const status of [400,403,404,409,426,428,503]) test(`generic ${status}, no fallback/retry`,async()=>{
  const s=setup();await s.init();s.context.respond=async()=>new Response(JSON.stringify({error:'private blocked moderation details'}),{status});
  await assert.rejects(s.run('loadOwnedNetwork()'),e=>e.status===status&&!e.body.error.includes('private'));
  assert.equal(s.calls.filter(c=>c.url.startsWith('/api/network')).length,1);
  assert.equal(s.run('social.mode'),'v2');
});
test('conversation list uses bounded header cursor, preview and unread without read writes',async()=>{
  const s=setup();await s.init();s.context.respond=async()=>new Response(JSON.stringify([detail()]),{headers:{'X-Next-Cursor':'list-next'}});
  await s.run('loadOwnedConversations()');await s.run('loadOwnedConversations(true)');
  assert.match(s.calls.at(-1).url,/limit=20&cursor=list-next/);
  assert.equal(s.run('social.conversations.length'),1);
  assert.match(s.run('ownedConversationsHtml()'),/message 4/);
  assert.match(s.run('ownedConversationsHtml()'),/4 unread/);
  assert.equal(s.calls.filter(c=>c.opts.method==='POST').length,0);
});
for(const status of [200,201]) test(`create ${status} uses real counterpart and server slug`,async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');s.context.respond=async()=>new Response(JSON.stringify(detail()),{status});
  await s.run("ownedNetworkAction('connections',3,'message')");
  const call=s.calls.find(c=>c.opts.method==='POST');assert.equal(call.url,'/api/conversations');assert.deepEqual(call.body,{targetUserId:11});assert.equal(s.state.msgSlug,'server-slug');
});
test('bounded history merges older overlap in sequence order and keeps oldest cursor',async()=>{
  const s=setup();await s.init();await s.run("loadOwnedHistory('server-slug')");
  s.context.respond=async()=>new Response(JSON.stringify({...detail(),messages:[message(1),message(2),message(3)],hasMore:false,nextCursor:null}));
  await s.run("loadOwnedHistory('server-slug',true)");assert.match(s.calls.at(-1).url,/before=older/);
  assert.equal(s.run("social.threads.get('server-slug').messages.map(m=>m.sequence).join(',')"),'1,2,3,4');
  s.context.respond=async()=>new Response(JSON.stringify(detail()));await s.run("loadOwnedHistory('server-slug')");
  assert.equal(s.run("social.threads.get('server-slug').nextCursor"),null);
  assert.equal(s.calls.filter(c=>c.opts.method==='POST').length,0);
});
async function readSetup(messages, lastReadSequence = 0) {
  const s = setup(); await s.init();
  s.context.respond = async () => new Response(JSON.stringify({...detail(), messages, lastReadSequence}));
  await s.run("loadOwnedHistory('server-slug')");
  s.state.view = 'messages'; s.state.msgSlug = 'server-slug';
  s.context.respond = async (url, opts) => new Response(JSON.stringify({lastReadSequence: JSON.parse(opts.body).upToSequence, unreadCount: 0}));
  s.posts = () => s.calls.filter(c => c.opts.method === 'POST').map(c => c.body.upToSequence);
  return s;
}
test('observations cannot skip incoming gaps; retained observations become contiguous', async () => {
  const s = await readSetup([message(1), message(2), message(3)]);
  await s.run("markOwnedRead('server-slug',3)"); assert.deepEqual(s.posts(), []);
  await s.run("markOwnedRead('server-slug',1)"); assert.deepEqual(s.posts(), [1]);
  await s.run("markOwnedRead('server-slug',2)"); assert.deepEqual(s.posts(), [1,3]);
  await s.run("markOwnedRead('server-slug',3)");
  await s.run("markOwnedRead('server-slug',1)");
  await s.run("markOwnedRead('server-slug',99)");
  assert.deepEqual(s.posts(), [1,3]);
  assert.equal(s.run("social.threads.get('server-slug').lastReadSequence"), 3);
});
test('own-message gap is non-blocking', async () => {
  const s = await readSetup([message(1), {...message(2), who:'me'}, message(3)]);
  await s.run("markOwnedRead('server-slug',3)"); assert.deepEqual(s.posts(), []);
  await s.run("markOwnedRead('server-slug',1)"); assert.deepEqual(s.posts(), [3]);
});
test('unloaded history blocks read until missing incoming messages are loaded and observed', async () => {
  const s = await readSetup([message(20)], 18);
  await s.run("markOwnedRead('server-slug',20)"); assert.deepEqual(s.posts(), []);
  s.context.respond = async () => new Response(JSON.stringify({...detail(), messages:[message(19)], lastReadSequence:18, hasMore:false}));
  await s.run("loadOwnedHistory('server-slug',true)");
  assert.deepEqual(s.posts(), []);
  s.context.respond = async () => new Response(JSON.stringify({lastReadSequence:20,unreadCount:0}));
  await s.run("markOwnedRead('server-slug',19)"); assert.deepEqual(s.posts(), [20]);
});
test('in-flight reads drain later contiguous observations once without regressing', async () => {
  const s = await readSetup([message(1), message(2), message(3)]); let finish;
  s.context.respond = () => new Promise(resolve => { finish = resolve; });
  const pending = s.run("markOwnedRead('server-slug',1)"); await new Promise(setImmediate);
  await s.run("markOwnedRead('server-slug',3)");
  await s.run("markOwnedRead('server-slug',2)"); assert.deepEqual(s.posts(), [1]);
  s.context.respond = async () => new Response(JSON.stringify({lastReadSequence:3,unreadCount:0}));
  finish(new Response(JSON.stringify({lastReadSequence:1,unreadCount:2}))); await pending;
  await new Promise(setImmediate); assert.deepEqual(s.posts(), [1,3]);
  await s.run("markOwnedRead('server-slug',2)"); assert.deepEqual(s.posts(), [1,3]);
});
test('hidden tabs block observations and in-flight continuation', async () => {
  const s = await readSetup([message(1), message(2)]); let finish;
  s.context.document.visibilityState = 'hidden';
  await s.run("markOwnedRead('server-slug',1)"); assert.deepEqual(s.posts(), []);
  s.context.document.visibilityState = 'visible';
  s.context.respond = () => new Promise(resolve => { finish = resolve; });
  const pending = s.run("markOwnedRead('server-slug',1)"); await new Promise(setImmediate);
  await s.run("markOwnedRead('server-slug',2)"); s.context.document.visibilityState = 'hidden';
  finish(new Response(JSON.stringify({lastReadSequence:1,unreadCount:1}))); await pending;
  await new Promise(setImmediate); assert.deepEqual(s.posts(), [1]);
});
test('failed read is not repeatedly posted for the same observed cursor', async () => {
  const s = await readSetup([message(1)]);
  s.context.respond = async () => {throw new Error('network failure');};
  await s.run("markOwnedRead('server-slug',1)"); await s.run("markOwnedRead('server-slug',1)");
  assert.deepEqual(s.posts(), [1]);
});
test('read-only retained history still advances contiguous own cursor', async () => {
  const s = await readSetup([message(1)]); s.run("social.threads.get('server-slug').readOnly=true");
  await s.run("markOwnedRead('server-slug',1)"); assert.deepEqual(s.posts(), [1]);
});
test('read-only UI disables send and retains escaped history',async()=>{
  const s=setup();await s.init();await s.run("loadOwnedHistory('server-slug')");s.run("social.threads.get('server-slug').readOnly=true");
  assert.match(s.run("ownedThreadHtml('server-slug')"),/read-only/);assert.match(s.run("ownedThreadHtml('server-slug')"),/required disabled/);
  await s.run("sendOwnedMessage({preventDefault(){},target:{text:'x'}},'server-slug')");assert.equal(s.calls.filter(c=>c.opts.method==='POST').length,0);
});
test('send failure retains same retry key/text; 200 retry merges one message; new submission uses new key',async()=>{
  const s=setup();await s.init();await s.run("loadOwnedHistory('server-slug')");
  s.context.respond=async()=>{throw new Error('lost response');};await s.run("sendOwnedMessage({preventDefault(){},target:{text:'hello'}},'server-slug')");
  const first=s.calls.find(c=>c.url.endsWith('/messages')).body;
  s.context.respond=async()=>new Response(JSON.stringify({message:{...message(5),who:'me',text:'hello'},lastSequence:5}),{status:200});
  await s.run("retryOwnedMessage('server-slug')");assert.deepEqual(s.calls.at(-1).body,first);assert.equal(s.run('social.retries.size'),0);
  s.context.respond=async()=>new Response(JSON.stringify({message:{...message(6),who:'me',text:'new'},lastSequence:6}),{status:201});
  await s.run("sendOwnedMessage({preventDefault(){},target:{text:'new'}},'server-slug')");
  assert.notEqual(s.calls.at(-1).body.clientMessageId,first.clientMessageId);
  assert.equal(s.run("social.threads.get('server-slug').messages.length"),4);assert.equal('who' in first,false);
});
test('send conflict clears retry, refreshes state, never replays',async()=>{
  const s=setup();await s.init();await s.run("loadOwnedHistory('server-slug')");
  s.context.respond=async(url,opts)=>new Response(JSON.stringify(opts.method==='POST'?{}:detail()),{status:opts.method==='POST'?409:200});
  await s.run("sendOwnedMessage({preventDefault(){},target:{text:'hello'}},'server-slug')");
  assert.equal(s.run('social.retries.size'),0);assert.equal(s.calls.filter(c=>c.url.endsWith('/messages')).length,1);
});
test('double submit shares one pending logical send',async()=>{
  const s=setup();await s.init();await s.run("loadOwnedHistory('server-slug')");let finish;
  s.context.respond=()=>new Promise(r=>{finish=r;});const pending=s.run("sendOwnedMessage({preventDefault(){},target:{text:'hello'}},'server-slug')");
  await new Promise(setImmediate);await s.run("sendOwnedMessage({preventDefault(){},target:{text:'hello'}},'server-slug')");
  assert.equal(s.calls.filter(c=>c.url.endsWith('/messages')).length,1);
  finish(new Response(JSON.stringify({message:message(5),lastSequence:5}),{status:201}));await pending;
});
for(const change of ['setCurrentUser(null,true)','setCurrentUser({id:2},true)','setCurrentUser({id:1},true)','clearCsrfState()']) test(`state/cursors/retries cleared: ${change}`,async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');await s.run("loadOwnedHistory('server-slug')");
  s.run("social.listCursor='old';social.retries.set('server-slug',{clientMessageId:'old'});social.busy.add('network');state.msgSlug='server-slug'");s.run(change);
  assert.equal(s.run('social.network'),null);assert.equal(s.run('social.listCursor'),null);assert.equal(s.run('social.threads.size'),0);assert.equal(s.run('social.retries.size'),0);assert.equal(s.run('social.busy.size'),0);assert.equal(s.state.msgSlug,null);
});
for(const operation of ['loadOwnedNetwork()',"loadOwnedHistory('server-slug')",'loadOwnedConversations()']) test(`late old-account result ignored: ${operation}`,async()=>{
  const s=setup();await s.init();let finish;s.context.respond=()=>new Promise(r=>{finish=r;});const pending=s.run(operation);await new Promise(setImmediate);
  s.run('setCurrentUser({id:2},true)');finish(new Response(JSON.stringify(detail())));await assert.rejects(pending,e=>e.stale);
  assert.equal(s.run('social.network'),null);assert.equal(s.run('social.threads.size'),0);assert.equal(s.run('social.conversations'),null);
});
test('late mutation cannot open old thread or copy retry to next account',async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');let finish;s.context.respond=()=>new Promise(r=>{finish=r;});const pending=s.run("ownedNetworkAction('connections',3,'message')");await new Promise(setImmediate);
  s.run('setCurrentUser({id:2},true)');finish(new Response(JSON.stringify(detail()),{status:201}));await pending;
  assert.equal(s.state.msgSlug,null);assert.equal(s.run('social.threads.size'),0);assert.equal(s.run('social.retries.size'),0);
});
test('401 invalidates session, late old 401 cannot sign out new account',async()=>{
  const s=setup();await s.init();s.context.respond=async()=>new Response('{}',{status:401});await assert.rejects(s.run('loadOwnedNetwork()'));assert.equal(s.state.user,null);
  const n=setup();await n.init();let finish;n.context.respond=()=>new Promise(r=>{finish=r;});const pending=n.run('loadOwnedNetwork()');await new Promise(setImmediate);n.run('setCurrentUser({id:2},true)');finish(new Response('{}',{status:401}));await assert.rejects(pending);assert.equal(n.state.user.id,2);
});
test('visible bubbles alone advance read; hidden tab and stale observer do not',async()=>{
  const s=await readSetup([message(3),message(4)],2);
  let observe;
  s.context.IntersectionObserver=class {constructor(fn){observe=fn;} observe(){} disconnect(){}};
  s.state.view='messages';s.state.msgSlug='server-slug';s.run('observeSocialMessages()');
  s.context.respond=async()=>new Response(JSON.stringify({lastReadSequence:3,unreadCount:1}));
  const entry={isIntersecting:true,intersectionRatio:1,target:{dataset:{socialSequence:'3'}}};
  s.context.document.visibilityState='hidden';observe([entry]);await new Promise(setImmediate);
  assert.equal(s.calls.filter(c=>c.opts.method==='POST').length,0);
  s.context.document.visibilityState='visible';observe([entry]);await new Promise(setImmediate);
  assert.deepEqual(s.calls.at(-1).body,{upToSequence:3});
  s.run('setCurrentUser({id:2},true)');observe([entry]);await new Promise(setImmediate);
  assert.equal(s.calls.filter(c=>c.opts.method==='POST').length,1);
});
test('late send response cannot refill new account history or retry state',async()=>{
  const s=setup();await s.init();await s.run("loadOwnedHistory('server-slug')");let finish;
  s.context.respond=()=>new Promise(r=>{finish=r;});const pending=s.run("sendOwnedMessage({preventDefault(){},target:{text:'old secret'}},'server-slug')");
  await new Promise(setImmediate);const key=s.calls.at(-1).body.clientMessageId;s.run('setCurrentUser({id:2},true)');
  finish(new Response(JSON.stringify({message:message(5),lastSequence:5}),{status:201}));await pending;
  assert.equal(s.run('social.retries.size'),0);assert.equal(s.run('social.threads.size'),0);
  s.context.respond=async()=>new Response(JSON.stringify(detail()));
  await s.init();await s.run("loadOwnedHistory('server-slug')");
  assert.ok(!s.calls.slice(-2).some(c=>c.body?.clientMessageId===key));
});
test('maintenance config sends no social request and never assumes legacy',async()=>{
  const s=setup();s.context.fetch=async(url,opts)=>{s.calls.push({url,opts});return new Response('{"mode":"maintenance"}');};
  await assert.rejects(s.run('socialMode()'),e=>e.status===503);assert.equal(s.calls.length,1);assert.equal(s.calls[0].url,'/api/social-config');
});
test('explicit legacy config retains no ownership header',async()=>{
  const s=setup();s.context.fetch=async(url,opts)=>{s.calls.push({url,opts});return new Response(JSON.stringify(url==='/api/social-config'?{mode:'legacy'}:net()));};
  assert.equal(await s.run('socialMode()'),'legacy');await s.run("socialRequest('/api/network')");assert.equal(s.calls.at(-1).opts.headers.has('X-Forge-Ownership-Version'),false);
});

test('401 during CSRF acquisition clears all social state without sending write',async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');
  s.context.fetch=async(url)=>{s.calls.push({url});return new Response('{}',{status:401});};
  await s.run("ownedNetworkAction('requests',1,'accept')");
  assert.equal(s.state.user,null);assert.equal(s.run('social.network'),null);assert.equal(s.calls.at(-1).url,'/api/auth/csrf-token');
});
test('CSRF rejection clears stale state and offers refresh without replay',async()=>{
  const s=setup();await s.init();await s.run('loadOwnedNetwork()');
  s.context.respond=async()=>new Response('{"code":"csrf_failed"}',{status:403});
  await s.run("ownedNetworkAction('requests',1,'accept')");
  assert.equal(s.run('social.network'),null);assert.equal(s.state.user.id,1);assert.match(s.elements.content.innerHTML,/Refresh/);
  assert.equal(s.calls.filter(c=>c.opts.method==='POST').length,1);
});

test('late read response and old observer cannot refill switched account', async () => {
  const s = await readSetup([message(1), message(2)]); let finish;
  s.context.respond = () => new Promise(resolve => {finish = resolve;});
  const pending = s.run("markOwnedRead('server-slug',1)"); await new Promise(setImmediate);
  await s.run("markOwnedRead('server-slug',2)");
  s.run('setCurrentUser({id:2},true)');
  finish(new Response(JSON.stringify({lastReadSequence:1,unreadCount:1}))); await pending;
  assert.deepEqual(s.posts(), [1]); assert.equal(s.run('social.threads.size'), 0);
});


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
