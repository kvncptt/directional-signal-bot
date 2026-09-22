(() => {
 const safe=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const clock=t=>new Date(t*1000).toLocaleString('en-US',{timeZone:'America/Detroit',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
 const count=(rows,h)=>{
  const n={WIN:0,LOSS:0,TIE:0,PENDING:0};rows.forEach(r=>n[r['result_'+h+'m']||'PENDING']++);
  const settled=n.WIN+n.LOSS+n.TIE;
  return `${n.WIN}W / ${n.LOSS}L / ${n.TIE}T${n.PENDING?' / '+n.PENDING+' pending':''} · ${settled?(100*n.WIN/settled).toFixed(1)+'%':'—'}`;
 };
 const describe=data=>data.signals.map(s=>{
  const index=data.candles.findIndex(c=>c.time===s.time),c=data.candles[index],ctx=s.trend_context;
  if(!c)return {...s};
  const sign=s.direction==='UP'?1:-1,width=c.high-c.low;
  const wick=width?(sign===1?c.high-Math.max(c.open,c.close):Math.min(c.open,c.close)-c.low)/width:null;
  const level=ctx?.[sign===1?'resistance':'support'];
  const prior=data.candles[index-5];
  const contiguous=prior&&data.candles.slice(index-5,index+1).every((b,j)=>b.time===prior.time+60*j);
  const move=contiguous?sign*(c.close-prior.close):null;
  return {...s,wick,room:level!=null&&ctx?.atr>0?Math.abs(level-c.close)/ctx.atr:null,
   aligned:ctx?.bias&&ctx.bias!=='UNCLEAR'?ctx.bias===s.direction:null,
   pullback:move==null?null:move<0,body:sign*(c.close-c.open)};
 });
 const charts={};
 function render(sid,data,chart){
  const target=document.getElementById(`focus-${sid}-analysis`);
  const rows=describe(data),approved=rows.filter(s=>s.admission==='APPROVED'),baseline=rows.filter(s=>s.admission==='BASELINE');
  const groups=[['All approved entries',approved],['Trend aligned',approved.filter(s=>s.aligned===true)],['Five-minute pullback, then directional body',approved.filter(s=>s.pullback===true&&s.body>0)],['Opposing wick ≥40%',approved.filter(s=>s.wick!=null&&s.wick>=.4)],['Opposing wick <40%',approved.filter(s=>s.wick!=null&&s.wick<.4)],['Opposing level ≤1 ATR',approved.filter(s=>s.room!=null&&s.room<=1)],['Opposing level >1 ATR',approved.filter(s=>s.room!=null&&s.room>1)]];
  const previous=target.querySelector('details')?.open;
  const scroll=target.querySelector('.entry-history')?.scrollTop||0;
  target.innerHTML=`<h3>Setup study · ${safe(data.pair.replace('_','/'))}</h3><p>Current broader trend: <b>${safe(data.trend?.bias||'Checking')}</b>. Primary comparison uses trend-approved entries only.</p>
  <div class="focus-metrics"><span><strong>${approved.length}</strong>approved entries</span><span><strong>${baseline.length}</strong>baseline entries</span><span><strong>${data.blocked_signals?.length||0}</strong>blocked setups</span></div>
  <div class="table-wrap"><table><thead><tr><th>Entry condition</th><th>Entries</th><th>1 minute</th><th>3 minutes</th></tr></thead><tbody>${groups.map(([label,g])=>`<tr><td>${label}</td><td>${g.length}</td><td>${count(g,1)}</td><td>${count(g,3)}</td></tr>`).join('')}</tbody></table></div>
  <p>Groups overlap. A pullback means net price movement against the signal over five contiguous minutes, followed by an entry candle closing in the signal direction. ATR scales distance by recent volatility. Missing context is excluded from that comparison.</p>
  <p><b>Early evidence, not a proven edge.</b> Ties count in the win-rate denominator. Adjacent signals share price movement; 1m and 3m outcomes are not independent. Wick and distance groupings are exploratory. Baseline: ${count(baseline,1)} (1m); ${count(baseline,3)} (3m).</p>
  <details ${previous?'open':''}><summary>Inspect all ${rows.length} recorded entries · wins and losses</summary><div class="table-wrap entry-history"><table><thead><tr><th>Entry · Detroit</th><th>Direction / status</th><th>1m / 3m</th><th>Trend / pullback</th><th>Opposing wick / level distance</th></tr></thead><tbody>${[...rows].reverse().map(s=>`<tr><td><button class="signal-link" data-entry="${s.time}">${clock(s.time)}</button><br>${Number(s.entry).toFixed(5)}</td><td>${safe(s.direction)}<br>${safe(s.admission)}</td><td>${safe(s.result_1m||'PENDING')} / ${safe(s.result_3m||'PENDING')}</td><td>${s.aligned==null?'Unknown':s.aligned?'Aligned':'Against trend'} / ${s.pullback==null?'Unknown':s.pullback?'Pullback':'No pullback'}</td><td>${s.wick==null?'—':(100*s.wick).toFixed(0)+'%'} / ${s.room==null?'No level/context':s.room.toFixed(2)+' ATR'}</td></tr>`).join('')}</tbody></table></div></details>`;
  target.querySelectorAll('[data-entry]').forEach(b=>b.onclick=()=>chart.selectSignal(Number(b.dataset.entry)));
  target.querySelector('.entry-history').scrollTop=scroll;
 }
 window.SetupStudy={render};
})();
