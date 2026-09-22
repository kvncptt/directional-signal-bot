let heatState=null,heatUpdated=0,selectedPair=null;
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const $=id=>document.getElementById(id),panels=new Map();
const admitted=t=>['APPROVED','BASELINE'].includes(t.admission);
const pct=x=>x==null?'—':(x*100).toFixed(1)+'%';
const time=x=>new Date(x).toLocaleTimeString('en-US',{timeZone:'America/Detroit',hour:'2-digit',minute:'2-digit'});
const stamp=x=>new Date(x).toLocaleString('en-US',{timeZone:'America/Detroit',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
function createPanel(sid,name){
 const prefix=`focus-${sid}-`,node=document.createElement('article');node.className='strategy-panel';node.setAttribute('aria-label',`Strategy ${sid} ${name}`);
 node.innerHTML=`<div class="panel-heading"><div><p class="eyebrow">STRATEGY ${esc(sid)}</p><h2>${esc(name)}</h2></div><span class="selected-pair-name" id="${prefix}pair-name"></span><label class="pair-picker" hidden>Pair<select id="${prefix}pair" aria-label="Strategy ${sid} pair"></select></label></div>
 <div class="pair-status"><span id="${prefix}feed"></span><span id="${prefix}trend"></span></div>
 <div class="metrics" id="${prefix}metrics"></div>
 <details class="horizon-details"><summary id="${prefix}horizon-label">Horizon comparison</summary><div id="${prefix}horizon-body"></div></details>
 <div class="chart-tools"><span id="${prefix}chart-title" class="sr-only"></span><label id="${prefix}ha-label" hidden><input id="${prefix}ha-toggle" type="checkbox" checked>Heikin Ashi</label><button id="${prefix}latest-signal">Latest entry</button><button id="${prefix}chart-reset">Live view</button></div>
 <div id="${prefix}price-chart" class="price-chart" role="img" aria-label="Strategy ${sid} selected pair candles and entries"></div>
 <p id="${prefix}chart-status" class="chart-status">Loading candles…</p>
 <div id="${prefix}chart-selection" class="chart-selection">Click an entry marker to inspect it.</div>
 <details class="chart-guide"><summary>Indicators &amp; entry rules</summary><div id="${prefix}chart-legend" class="chart-legend"></div><p id="${prefix}chart-rule"></p><a href="https://www.tradingview.com/" target="_blank" rel="noopener">Charts by TradingView</a></details>
 <details class="entry-details"><summary>Entries &amp; outcomes <span id="${prefix}entry-count"></span></summary><div class="entry-tools"><label>Show <select id="${prefix}filter"><option value="all">Recorded entries</option><option value="pending">Pending</option><option value="win">At least one win</option><option value="loss">At least one loss</option><option value="blocked">Filtered setups</option></select></label><a id="${prefix}export">Export CSV ↗</a></div><div class="table-wrap"><table><thead><tr><th>Entry · Detroit</th><th>Direction / price</th><th>1m</th><th>3m</th><th>Admission</th></tr></thead><tbody id="${prefix}entries"></tbody></table></div><p class="muted">UP wins above entry; DOWN wins below entry. Equal closes are ties.</p></details>
 <details class="study-details"><summary>Setup analysis</summary><div id="${prefix}analysis"></div></details>`;
 $('panels').append(node);
 const panel={sid,prefix,node,feeds:[],selected:null,data:null};panels.set(sid,panel);
 panel.chart=window.createPairChart(prefix,data=>{panel.data=data;if(node.querySelector('.study-details').open)window.SetupStudy.render(sid,data,panel.chart)});
 $(prefix+'pair').onchange=()=>{panel.selected=$(prefix+'pair').value;panel.data=null;$(prefix+'analysis').textContent='Loading this pair’s analysis…';updatePanel(panel)};
 $(prefix+'filter').onchange=()=>renderEntries(panel);
 node.querySelector('.study-details').ontoggle=()=>{if(panel.data&&node.querySelector('.study-details').open)window.SetupStudy.render(sid,panel.data,panel.chart)};
 return panel;
}
function renderEntries(p){
 const feed=p.feeds.find(x=>x.id===p.selected);if(!feed)return;
 const f=$(p.prefix+'filter').value;
 const rows=feed.trades.filter(t=>f==='blocked'?['BLOCKED','CHECKING'].includes(t.admission):admitted(t)&&(f==='all'||f==='pending'&&(!t.result_1m||!t.result_3m)||f==='win'&&(t.result_1m==='WIN'||t.result_3m==='WIN')||f==='loss'&&(t.result_1m==='LOSS'||t.result_3m==='LOSS')));
 const result=(t,h)=>`<span class="${esc(t['result_'+h+'m']||'PENDING')}">${esc(t['result_'+h+'m']||'PENDING')}</span><small>${t['close_'+h+'m']==null?'':Number(t['close_'+h+'m']).toFixed(feed.pair.endsWith('JPY')?3:5)}</small>`;
 $(p.prefix+'entries').innerHTML=rows.map(t=>`<tr><td><button class="signal-link" data-entry="${Date.parse(t.timestamp)/1000}">${stamp(t.timestamp)}</button></td><td>${esc(t.direction)}<small>${Number(t.entry).toFixed(feed.pair.endsWith('JPY')?3:5)}</small></td><td>${result(t,1)}</td><td>${result(t,3)}</td><td><span title="${esc(t.gate_reason)}">${esc(t.admission)}</span></td></tr>`).join('')||'<tr><td colspan="5" class="empty">No entries match this view.</td></tr>';
 $(p.prefix+'entries').querySelectorAll('[data-entry]').forEach(b=>b.onclick=()=>p.chart.selectSignal(Number(b.dataset.entry)));
 $(p.prefix+'entry-count').textContent=feed.trades.filter(admitted).length;
 $(p.prefix+'export').href='/export.csv?strategy='+encodeURIComponent(feed.id);
}
function updatePanel(p){
 const feed=p.feeds.find(x=>x.id===p.selected);if(!feed)return;
 $(p.prefix+'pair-name').textContent=feed.pair.replace('_',' / ');
 $(p.prefix+'feed').textContent=`${feed.state==='live'?'● Live':feed.state} · ${feed.price==null?'—':Number(feed.price).toFixed(feed.pair.endsWith('JPY')?3:5)}`;
 $(p.prefix+'feed').title=feed.message||'';
 $(p.prefix+'trend').textContent='Trend '+(feed.trend?.bias||'checking');
 const summary=h=>{const n=feed.summary[h]||{};return `<div><span>${h} minute${Number(h)===feed.primary_horizon?' · PRIMARY':''}</span><strong>${pct(n.rate)}</strong><small>${n.WIN||0}W · ${n.LOSS||0}L · ${n.TIE||0}T${n.PENDING?' · '+n.PENDING+' pending':''}</small></div>`};
 $(p.prefix+'metrics').innerHTML=`<div><span>Pair entries</span><strong>${feed.trades.filter(admitted).length}</strong><small>${feed.blocked_count||0} blocked</small></div>${summary('1')}${summary('3')}`;
 renderHorizon(p);renderEntries(p);p.chart.refresh(p.selected);
}
async function refresh(){
 try{
  const response=await fetch('/api/state');if(!response.ok)throw Error();const state=await response.json();
  heatState=state;heatUpdated=Date.now();drawHeat();
  $('cross-status').hidden=!state.cross_trial;
  if(state.cross_trial)$('cross-status').textContent=`Strategies 01 + 02: 3m focus · Strategies 03 + 08: 1m focus · four pairs each · trial ${stamp(state.cross_trial.start)} to ${stamp(state.cross_trial.end)} Detroit. Both outcomes recorded; each group’s trial results are separate from earlier entries.`;
  renderSelectedPair();
  const live=state.strategies.filter(f=>f.state==='live').length;
  $('session-status').textContent=`${state.phase==='collecting'?'Collecting':state.phase.replaceAll('_',' ')} · ${live}/${state.strategies.length} strategy/pair monitors · ${state.schedule==='weekdays'?'Mon–Fri':'Timed session'}`;
  const issues=state.strategies.filter(f=>f.state!=='live');
  $('notice').hidden=!issues.length&&state.phase==='collecting';
  $('notice').textContent=state.phase==='collecting'?issues.map(f=>f.pair.replace('_','/')+': '+(f.message||f.state)).join(' · '):`Session: ${state.phase.replaceAll('_',' ')}. Displayed charts and results are saved data.`;
 }catch{$('notice').hidden=false;$('notice').textContent='Dashboard connection lost. Displayed data may be out of date.'}
}
setInterval(()=>{$('clock').textContent=time(new Date())+' Detroit'},1000);refresh();setInterval(refresh,5000);

async function londonNotes(){
 try{const r=await fetch('/api/london');if(!r.ok)throw Error();const d=await r.json();
 const fresh=d.heartbeat&&Date.now()-Date.parse(d.heartbeat)<120000;
 $('london-status').textContent=!fresh?'Recorder unavailable':d.active?'Session open':'Next open '+new Date(d.next_open).toLocaleString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})+' London';
 const counts=n=>`${n.WIN}W / ${n.LOSS}L / ${n.TIE}T`+(n.PENDING?` / ${n.PENDING} pending`:'');
 $('london-notes').innerHTML=d.notes.length?'<table><thead><tr><th>Hour · London</th><th>Pair</th><th>Price observation</th><th>1m results</th><th>3m results</th><th>Coverage</th></tr></thead><tbody>'+d.notes.map(n=>`<tr><td>${esc(new Date(n.hour).toLocaleString('en-GB',{timeZone:'Europe/London',day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'}))}</td><td>${esc(n.symbol.replace('_','/'))}</td><td>${esc(n.note)}</td><td>${counts(n.outcomes['1'])}</td><td>${counts(n.outcomes['3'])}</td><td>${esc(n.status)} · ${n.candles}/60<small>${esc(n.collection)}</small></td></tr>`).join('')+'</tbody></table>':'<p class="muted">Waiting for London-session candles. The first full note is ready after 09:00 London.</p>';
 }catch{$('london-status').textContent='Recorder unavailable'}
}
londonNotes();setInterval(londonNotes,30000);

function renderSelectedPair(){
 if(!heatState)return;
 if(!heatState.strategies.some(f=>f.pair===selectedPair))selectedPair=heatState.strategies[0]?.pair;
 const chosen=heatState.strategies.filter(f=>f.pair===selectedPair).sort((a,b)=>(a.strategy_id||a.id).localeCompare(b.strategy_id||b.id));
 for(const p of panels.values())p.node.hidden=true;
 for(const feed of chosen){
  const sid=feed.strategy_id||feed.id,p=panels.get(sid)||createPanel(sid,feed.name);
  p.feeds=heatState.strategies.filter(f=>(f.strategy_id||f.id)===sid);
  if(p.selected!==feed.id){p.data=null;$(p.prefix+'analysis').textContent='Loading this pair’s analysis…'}
  p.selected=feed.id;p.node.hidden=false;
  $(p.prefix+'pair').innerHTML=`<option value="${esc(feed.id)}">${esc(feed.pair)}</option>`;
  $('panels').append(p.node);updatePanel(p);
 }
 $('selected-pair-heading').textContent=selectedPair?selectedPair.replace('_',' / ')+' · strategy comparison':'Choose a pair';
 drawHeat();
}
function selectPair(pair){
 selectedPair=pair;renderSelectedPair();
 $('selected-pair-heading').scrollIntoView({behavior:'smooth',block:'start'});
}
function drawHeat(){
 if(!heatState)return;
 const connected=Date.now()-heatUpdated<15000;
 $('quality-status').textContent=heatState.quality_policy?'Strategy 08 · Quality v2 paper trial':'Original trend policy';
 const root=$('pair-heat'),groups=new Map();
 for(const f of heatState.strategies){if(!groups.has(f.pair))groups.set(f.pair,[]);groups.get(f.pair).push(f)}
 root.querySelectorAll('[data-pair]').forEach(b=>{if(!groups.has(b.dataset.pair))b.remove()});
 for(const [pair,feeds] of groups){
  feeds.sort((a,b)=>(a.strategy_id||a.id).localeCompare(b.strategy_id||b.id));
  const labels=[];
  const halves=feeds.map(f=>{
   const h=f.heat||{state:'COLD',reason:'Waiting for setup assessment.'};
   const remaining=h.expires?Math.max(0,Math.ceil((Date.parse(h.expires)-Date.now())/1000)):0;
   const status=!connected?'OFFLINE':h.state==='HOT'&&!remaining?'COLD':h.state;
   const reason=!connected?'Dashboard connection stale.':h.state==='HOT'&&!remaining?'Measurement window ended; awaiting next assessment.':h.reason;
   const detail=status==='HOT'?`${h.direction} · ${Math.floor(remaining/60)}:${String(remaining%60).padStart(2,'0')} left`:h.total?`${h.met}/${h.total} conditions · ${h.direction}`:'Awaiting data';
   const sid=f.strategy_id||f.id;labels.push(`Strategy ${sid}: ${status}`);
   const checks=(h.checks||[]).map(c=>`${c.met?'✓':'○'} ${c.name}`).join(' · ');
   return `<span class="heat-half ${status.toLowerCase()}" title="${esc(reason+' '+checks)}"><span class="heat-strategy">Strategy ${esc(sid)} · ${f.primary_horizon||3}m</span><span class="heat-tag">${status}</span><small>${esc(detail)}</small><span class="heat-reason">${esc(reason)}</span></span>`;
  }).join('');
  let card=Array.from(root.children).find(b=>b.dataset.pair===pair);
  if(!card){card=document.createElement('button');card.dataset.pair=pair;card.onclick=()=>selectPair(pair);root.appendChild(card)}
  card.className='pair-heat-card';card.setAttribute('aria-pressed',String(pair===selectedPair));
  card.setAttribute('aria-label',`${pair.replace('_','/')}. ${labels.join('. ')}. Show both strategy charts`);
  const markup=`<span class="pair-card-heading"><strong>${esc(pair.replace('_','/'))}</strong><span>${pair===selectedPair?'Viewing':'Compare ↗'}</span></span><span class="heat-halves">${halves}</span>`;
  if(card.innerHTML!==markup)card.innerHTML=markup;
 }
}
setInterval(drawHeat,1000);

function renderHorizon(p){
 const a=heatState?.horizon_analysis?.[p.sid];if(!a)return;
 const current=a.cohorts[a.current];
 $(p.prefix+'horizon-label').textContent=`Primary: ${p.feeds[0]?.primary_horizon||3}m · Evidence: ${current.overall.label} · ${current.overall.n} matched entries`;
 const row=(name,c)=>`<tr><td>${esc(name)}</td><td>${c.n}</td><td>${pct(c.rates['1'])}</td><td>${pct(c.rates['3'])}</td><td>${esc(c.label)}</td></tr>`;
 $(p.prefix+'horizon-body').innerHTML='<p class="muted">Approved entries only, with both outcomes settled. Ties count as non-wins. Early leads are descriptive; samples are small and entries can overlap. Both horizons remain recorded.</p>'+Object.entries(a.cohorts).map(([version,d])=>`<p><strong>${esc(version===a.current?'Current rules':'Earlier rules')} · ${esc(version)}</strong></p><div class="table-wrap"><table><thead><tr><th>Scope</th><th>Entries</th><th>1m wins</th><th>3m wins</th><th>Assessment</th></tr></thead><tbody>${row('All assigned pairs',d.overall)}${Object.entries(d.pairs).map(([pair,c])=>row(pair.replace('_','/'),c)).join('')}</tbody></table></div><p class="muted">${d.overall.only_1m_wins} entries won only at 1m; ${d.overall.only_3m_wins} won only at 3m. ${d.overall.unresolved} approved entries await both outcomes.</p>`).join('');
}
