const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const html = fs.readFileSync('static/forge_demo.html', 'utf8');
const data = total => ({profileViews:{total:2,series:[]},connections:{total,series:[]},
  engagement:{likes:3,comments:4},peerComparison:{me:40,programmeAvg:50,programme:'Software'},topSearchedSkills:[]});
function setup() {
  const calls = [], content = {innerHTML:'new account content',setAttribute() {}};
  const user = {id:1,role:'trade',name:'A',skills:[],portfolio:{},visibility:{}};
  const context = vm.createContext({Headers, state:{user,view:'profile'},navigator:{onLine:true},
    esc:String,prettyRole:String,avatarHtml:()=>'',sparkline:()=>'<svg></svg>',barChart:()=>'<svg></svg>',
    document:{getElementById:()=>content},setTimeout,clearTimeout,enhanceAccessibility:()=>{},
    observeSocialMessages:()=>{},renderError:()=> 'error',viewTitle:()=> 'Profile',
    fetch:async (path,opts)=>{calls.push({path,opts});return path==='/api/auth/me'
      ? new Response(JSON.stringify(user)) : context.reply();},reply:()=>new Response(JSON.stringify(data(1)))});
  const run = code => vm.runInContext(code,context);
  run(html.slice(html.indexOf('let csrfToken = null;'),html.indexOf('let toastTimer = null;')));
  run(html.slice(html.indexOf('let profileExportBusy = false;'),html.indexOf('async function toggleVisibility(')));
  run(html.slice(html.indexOf('async function studentAnalyticsHtml()'),html.indexOf('async function renderListingsView()')));
  run(html.slice(html.indexOf('let viewLoadGeneration = 0;'),html.indexOf('async function renderFeedView()')));
  return {run,context,calls,content};
}
for(const total of [0,2]) test(`unchanged analytics shape renders ${total} connections without graph selection`,async()=>{
  const s=setup();s.context.reply=()=>new Response(JSON.stringify(data(total)));
  const rendered=await s.run('studentAnalyticsHtml()');
  assert.match(rendered,new RegExp(`stat-value">${total}</div>\\s*<div class="stat-label">Connections`));
  assert.match(rendered,/Connection growth/);
  assert.equal(s.calls.length,1);assert.equal(s.calls[0].path,'/api/analytics/student');
  assert.equal(s.calls[0].opts.headers.get('X-Forge-Ownership-Version'),null);
});
test('maintenance analytics failure leaves profile controls available',async()=>{
  const s=setup();s.context.reply=()=>new Response('{"error":"social maintenance"}',{status:503});
  const rendered=await s.run('renderProfileView()');
  assert.match(rendered,/Your profile/);assert.match(rendered,/profile-export/);
  assert.doesNotMatch(rendered,/Your insights|social maintenance/);
});
for(const phase of ['http','json']) test(`late old-account analytics ${phase} cannot repaint new account`,async()=>{
  const s=setup();let finish,started;
  const reached=new Promise(resolve=>{started=resolve;});
  s.context.reply=()=> phase==='http' ? new Promise(resolve=>{finish=resolve;started();})
    : {ok:true,json:()=>new Promise(resolve=>{finish=resolve;started();})};
  const pending=s.run('loadView()');await reached;
  s.run('setCurrentUser({id:2,role:"trade",name:"B"},true)');
  s.content.innerHTML='new account content';
  finish(phase==='http' ? new Response(JSON.stringify(data(99))) : data(99));await pending;
  assert.equal(s.content.innerHTML,'new account content');
});
