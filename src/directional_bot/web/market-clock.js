(() => {
 let schedule=null,lastFetch=0,retryAt=0,loading=false;
 const track=document.getElementById('market-clock-track');
 const safe=x=>String(x).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 const fmt=t=>new Date(t*1000).toLocaleString('en-US',{timeZone:'America/Detroit',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
 function draw(){
  if(!schedule)return;const now=Date.now()/1000,width=Math.max(240,track.clientWidth),span=86400,left=now-span/2;
  const x=t=>(t-left)/span*width;let shapes='';
  for(let t=Math.ceil(left/3600)*3600;t<left+span;t+=3600){const pos=x(t),date=new Date(t*1000);shapes+=`<line x1="${pos}" x2="${pos}" y1="29" y2="216" class="session-gridline"/>`;
   if(date.getUTCHours()% (width<500?6:3)===0&&Math.abs(pos-width/2)>34)shapes+=`<text x="${pos}" y="20" text-anchor="middle" class="session-tick">${safe(date.toLocaleTimeString('en-US',{timeZone:'America/Detroit',hour:'numeric'}))}</text>`;
  }
  for(const [i,s] of schedule.sessions.entries()){
   const y=36+i*34;shapes+=`<rect x="0" y="${y}" width="${width}" height="24" rx="4" class="session-row"/>`;
   for(const win of schedule.windows.filter(w=>w.key===s.key&&w.end>left&&w.start<left+span)){
    const a=Math.max(0,x(win.start)),b=Math.min(width,x(win.end));
    shapes+=`<rect x="${a}" y="${y}" width="${b-a}" height="24" rx="4" class="session-band ${s.key}"><title>${safe(s.name)} · ${fmt(win.start)}–${fmt(win.end)} Detroit</title></rect>`;
   }
  }
  for(const win of schedule.overlaps.filter(w=>w.end>left&&w.start<left+span)){
   const a=Math.max(0,x(win.start)),b=Math.min(width,x(win.end));
   shapes+=`<rect x="${a}" y="172" width="${b-a}" height="22" rx="3" class="session-overlap"><title>${safe(win.names.join(' + '))} · ${fmt(win.start)}–${fmt(win.end)} Detroit</title></rect>`;
   if(b-a>80)shapes+=`<text x="${(a+b)/2}" y="187" text-anchor="middle" class="overlap-count">${win.names.length} sessions</text>`;
  }
  shapes+=`<line x1="${width/2}" x2="${width/2}" y1="27" y2="216" class="session-now-line"/><rect x="${width/2-23}" y="4" width="46" height="19" rx="5" class="session-now-tag"/><text x="${width/2}" y="17" text-anchor="middle" class="session-now-text">NOW</text><text x="0" y="231" class="session-tick">${safe(fmt(left))}</text><text x="${width}" y="231" text-anchor="end" class="session-tick">${safe(fmt(left+span))}</text>`;
  track.innerHTML=`<svg width="100%" height="240" viewBox="0 0 ${width} 240" aria-hidden="true">${shapes}</svg>`;
  const active=schedule.windows.filter(w=>w.start<=now&&now<w.end).map(w=>w.name);
  const future=schedule.windows.flatMap(w=>[{t:w.start,label:w.name+' opens'},{t:w.end,label:w.name+' closes'}]).filter(v=>v.t>now).sort((a,b)=>a.t-b.t)[0];
  const label=active.length?active.join(' + ')+(active.length>1?' overlapping now':' active now'):'Between scheduled sessions';
  document.getElementById('market-clock-active').textContent=label+(future?' · Next: '+future.label+' in '+Math.ceil((future.t-now)/60)+' min':'');
  document.getElementById('market-clock-now').textContent=new Date().toLocaleString('en-US',{timeZone:'America/Detroit',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit',second:'2-digit'})+' Detroit';
  track.setAttribute('aria-label',label+'. Current time centered; previous and next twelve hours.');
 }
 async function load(){if(loading)return;loading=true;try{const r=await fetch('/api/market-clock');if(!r.ok)throw Error();schedule=await r.json();lastFetch=Date.now();draw()}catch{document.getElementById('market-clock-active').textContent='Session schedule unavailable. Retrying…';retryAt=Date.now()+30000}finally{loading=false}}
 load();setInterval(()=>{if(Date.now()-lastFetch>900000&&Date.now()>=retryAt)load();else draw()},1000);new ResizeObserver(draw).observe(track);
})();
