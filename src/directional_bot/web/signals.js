/* Pure view model. Entry time defines expiry; refresh never resets the clock. */
function activeSignalGroups(state, now=Date.now()) {
 if(!state || state.phase!=='collecting')return [];
 const groups=new Map(),assigned=new Map();
 for(const f of state.strategies){
  const sid=f.strategy_id||f.id;
  if(!assigned.has(f.pair))assigned.set(f.pair,new Set());assigned.get(f.pair).add(sid);
  if(f.state!=='live'||f.heat?.state==='OFFLINE'||!f.last_close||now-Date.parse(f.last_close)>90000)continue;
  const horizon=f.primary_horizon||3;
  for(const t of f.trades){
   const start=Date.parse(t.timestamp),expires=start+horizon*60000;
   if(t.admission!=='APPROVED'||!['UP','DOWN'].includes(t.direction)||!(start<=now&&now<expires))continue;
   const key=[f.pair,t.direction,horizon].join(':');
   if(!groups.has(key))groups.set(key,{key,pair:f.pair,direction:t.direction,horizon,entries:new Map()});
   const g=groups.get(key),old=g.entries.get(sid);
   if(!old||start>old.start)g.entries.set(sid,{strategy:sid,start,expires,price:t.entry});
  }
 }
 return [...groups.values()].map(g=>({...g,entries:[...g.entries.values()].sort((a,b)=>a.strategy.localeCompare(b.strategy)),votes:g.entries.size,total:assigned.get(g.pair).size})).sort((a,b)=>b.votes-a.votes||a.pair.localeCompare(b.pair)||a.direction.localeCompare(b.direction));
}
function pastSignals(state,now=Date.now()){
 const rows=[],seen=new Set();
 for(const f of state?.strategies||[]){
  const sid=f.strategy_id||f.id,horizon=f.primary_horizon||3;
  for(const t of f.trades){
   const start=Date.parse(t.timestamp),expires=start+horizon*60000;
   const key=[f.pair,sid,t.timestamp,horizon].join(':');
   if(t.admission!=='APPROVED'||!['UP','DOWN'].includes(t.direction)||!(expires<=now)||seen.has(key))continue;
   seen.add(key);
   const outcome=t[`result_${horizon}m`];
   rows.push({key,pair:f.pair,strategy:sid,direction:t.direction,horizon,start,expires,entry:t.entry,close:t[`close_${horizon}m`],outcome:['WIN','LOSS','TIE'].includes(outcome)?outcome:'PENDING'});
  }
 }
 return rows.sort((a,b)=>b.start-a.start||a.pair.localeCompare(b.pair)||a.strategy.localeCompare(b.strategy));
}
if(typeof module!=='undefined')module.exports={activeSignalGroups,pastSignals};
