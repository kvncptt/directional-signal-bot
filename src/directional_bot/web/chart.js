window.createPairChart = function(prefix="", onData=()=>{}) {
 const L=window.LightweightCharts, el=id=>document.getElementById(prefix+id);
 const colors=['#5ce4b3','#70aaff','#ffbe68','#d39bff','#ff8496','#b1c5da'];
 const fmt=t=>new Date(t*1000).toLocaleTimeString('en-US',{timeZone:'America/Detroit',hour:'2-digit',minute:'2-digit'});
 const escape=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
 let chart=null,candles=null,series=[],markerApi=null,entryLine=null,current=null,requested=null,signalTime=null,revision=null,loading=false;
 const px=v=>v==null?'pending':Number(v).toFixed(current?.pair==='USD_JPY'?3:5);
 function reset(){if(chart)chart.remove();chart=null;entryLine=null;series=[];markerApi=null;signalTime=null;revision=null;current=null;el('chart-legend').replaceChildren();el('chart-selection').textContent='Click an entry arrow or a signal time below to inspect it.';}
 function create(data){
  chart=L.createChart(el('price-chart'),{autoSize:true,layout:{background:{color:'#101a28'},textColor:'#a9bad1',attributionLogo:true,panes:{separatorColor:'#2a3b52',separatorHoverColor:'#4c709b'}},grid:{vertLines:{color:'#182739'},horzLines:{color:'#1d2c40'}},rightPriceScale:{borderColor:'#30415b'},timeScale:{timeVisible:true,secondsVisible:false,borderColor:'#30415b',tickMarkFormatter:t=>fmt(t)},localization:{timeFormatter:t=>fmt(t)+' Detroit'},crosshair:{mode:L.CrosshairMode.Normal}});
  const precision=data.pair==='USD_JPY'?3:5;
  candles=chart.addSeries(L.CandlestickSeries,{upColor:'#5ce4b3',downColor:'#ff8496',wickUpColor:'#5ce4b3',wickDownColor:'#ff8496',borderVisible:false,priceFormat:{type:'price',precision,minMove:10**-precision}});
  markerApi=L.createSeriesMarkers(candles,[]);
  for(const line of data.lines){
   const s=chart.addSeries(line.kind==='histogram'?L.HistogramSeries:L.LineSeries,{color:line.color,lineWidth:line.name.includes('Trend')?2:line.pane?2:1,lineStyle:line.dashed?L.LineStyle.Dashed:L.LineStyle.Solid,lastValueVisible:false,priceLineVisible:false,title:line.name,priceFormat:{type:'price',precision:line.name.includes('MACD')?6:line.pane?2:precision,minMove:line.name.includes('MACD')?0.000001:line.pane?0.01:10**-precision}},line.pane);
   for(const level of line.levels)s.createPriceLine({price:level,color:'#63758d',lineWidth:1,lineStyle:L.LineStyle.Dashed,axisLabelVisible:true,title:String(level)});
   series.push(s);
  }
  // Unconnected points preserve the actual raw-close entry even on HA candles.
  for(const direction of ['UP','DOWN'])series.push(chart.addSeries(L.LineSeries,{color:direction==='UP'?'#5ce4b3':'#ff8496',lineVisible:false,pointMarkersVisible:true,pointMarkersRadius:5,lastValueVisible:false,priceLineVisible:false,title:direction+' entries'}));
  chart.subscribeClick(param=>{if(!param.time||!current)return;const signal=[...current.signals,...(current.blocked_signals||[])].find(s=>s.time===param.time);if(signal)selectSignal(signal.time,false)});
  const panes=chart.panes();panes[0].setHeight(panes.length>2?320:380);for(let i=1;i<panes.length;i++)panes[i].setHeight(140);
 }
 function plot(data){
  const changed=!current||current.strategy!==data.strategy||current.strategy_id!==data.strategy_id||current.run_id!==data.run_id;
  if(changed){reset();current=data;if(data.candles.length)create(data)}
  current=data;
  el('chart-title').textContent=data.pair.replace('_',' / ')+' · 1 minute · '+data.name;
  el('ha-label').hidden=(data.strategy_id||data.strategy)!=='04';
  el('chart-rule').textContent=data.rule+(data.trend_policy?' Trend gate: '+(data.trend?.bias||'checking')+'. UP requires an uptrend; DOWN requires a downtrend. Unclear trend or nearby opposing level blocks entry.':'');
  if(!data.candles.length){el('chart-status').textContent='Waiting for this pair’s first completed candles';return;}
  if(!chart)create(data);
  const ha=(data.strategy_id||data.strategy)==='04'&&el('ha-toggle').checked;
  const nextRevision=data.run_id+':'+data.strategy+':'+data.candles.at(-1).time+':'+ha+':'+JSON.stringify(data.signals)+':'+JSON.stringify(data.blocked_signals||[]);
  el('chart-status').textContent=(ha?'Heikin Ashi view · ':'Candlestick view · ')+data.candles.length+' candles · last close '+fmt(data.candles.at(-1).time)+' Detroit';
  if(nextRevision===revision)return;
  const range=chart.timeScale().getVisibleLogicalRange();
  const oldLength=candles.data().length;
  const follow=!range||range.to>=oldLength-3;
  candles.setData(ha?data.ha:data.candles);
  data.lines.forEach((line,i)=>series[i].setData(line.data.map(p=>line.kind==='histogram'?{...p,color:p.value>=0?'#339d80':'#be566e'}:p)));
  ['UP','DOWN'].forEach((dir,i)=>series[data.lines.length+i].setData(data.signals.filter(s=>s.direction===dir).map(s=>({time:s.time,value:s.entry}))));
  const markers=data.confirmations.map(m=>({time:m.time,position:m.direction==='UP'?'belowBar':'aboveBar',color:'#bca1e5',shape:'circle',text:m.name}));
  for(const s of data.signals)markers.push({time:s.time,position:s.direction==='UP'?'belowBar':'aboveBar',color:s.direction==='UP'?'#5ce4b3':'#ff8496',shape:s.direction==='UP'?'arrowUp':'arrowDown',text:s.direction+' @ '+px(s.entry)});
  for(const s of data.blocked_signals||[])markers.push({time:s.time,position:'aboveBar',color:'#99a8bd',shape:'circle',text:'Blocked '+s.direction});
  markerApi.setMarkers(markers.sort((a,b)=>a.time-b.time));
  el('chart-legend').innerHTML=data.lines.map((l,i)=>`<span class="line-color ${colors.includes(l.color)?'c'+colors.indexOf(l.color):l.color==='#ffffff'?'trendwhite':'trendpurple'}">━ ${escape(l.name)}${l.pane?' · panel '+l.pane:''}</span>`).join('')+'<span class="line-color c0">● UP entry</span><span class="line-color c4">● DOWN entry</span>';
  if(changed||!range)chart.timeScale().setVisibleLogicalRange({from:Math.max(0,data.candles.length-90),to:data.candles.length+3});
  else if(follow)chart.timeScale().setVisibleLogicalRange({from:range.from+data.candles.length-oldLength,to:range.to+data.candles.length-oldLength});
  else chart.timeScale().setVisibleLogicalRange(range);
  revision=nextRevision;
  if(signalTime)selectSignal(signalTime,false);
 }
 function selectSignal(t,focus=true){
  if(!current||!chart)return;
  const s=[...current.signals,...(current.blocked_signals||[])].find(x=>x.time===Number(t));if(!s)return;signalTime=s.time;
  if(entryLine)candles.removePriceLine(entryLine);
  entryLine=candles.createPriceLine({price:s.entry,color:s.direction==='UP'?'#5ce4b3':'#ff8496',lineStyle:L.LineStyle.Dashed,lineWidth:2,axisLabelVisible:true,title:s.direction+' entry'});
  const values=current.lines.map(l=>{const v=l.data.find(p=>p.time===s.time);return v?l.name+' '+v.value.toFixed(l.pane&&!l.name.includes('MACD')?2:5):null}).filter(Boolean);
  el('chart-selection').innerHTML=`<strong>${fmt(s.time)} · ${escape(s.direction)} entry ${px(s.entry)}</strong><span>1m: ${px(s.close_1m)} · ${escape(s.result_1m||'PENDING')} &nbsp; / &nbsp; 3m: ${px(s.close_3m)} · ${escape(s.result_3m||'PENDING')}</span><span class="entry-indicators">${escape(s.admission||'BASELINE')}: ${escape(s.gate_reason||'Original signal before filtering.')}</span><span class="entry-indicators">At entry: ${escape(values.join(' · '))}</span>`;
  if(focus){const index=current.candles.findIndex(c=>c.time===s.time);chart.timeScale().setVisibleLogicalRange({from:Math.max(0,index-35),to:index+15});el('price-chart').scrollIntoView({behavior:'smooth',block:'center'});}
 }
 async function refresh(id){
  if(requested!==id){requested=id;reset();el('chart-status').textContent='Loading selected pair…';el('chart-title').textContent='Strategy '+id;}
  if(loading)return;
  loading=true;const sid=requested;
  try{const r=await fetch('/api/chart?strategy='+sid);if(!r.ok)throw Error('chart');const data=await r.json();if(requested===sid){plot(data);onData(data)}}catch{if(requested===sid)el('chart-status').textContent='Chart unavailable. Retrying…';}finally{loading=false;if(requested!==sid)refresh(requested)}
 }
 const api={refresh,selectSignal,destroy:reset};
 const bind=()=>{
  el('latest-signal').onclick=()=>{if(current?.signals.length)selectSignal(current.signals.at(-1).time);else el('chart-selection').textContent='No recorded entry for this strategy yet.'};
  el('chart-reset').onclick=()=>{if(chart&&current)chart.timeScale().setVisibleLogicalRange({from:Math.max(0,current.candles.length-90),to:current.candles.length+3})};
  el('ha-toggle').onchange=()=>{revision=null;if(current)plot(current)};
 };
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
 return api;
};

