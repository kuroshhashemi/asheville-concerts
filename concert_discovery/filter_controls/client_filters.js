// Canonical browser-side filtering. The table copy is generated from this file.
(function(root){
 const views=['To Review','Hidden','Interested','Going','All'];
 const statuses={'To Review':['Unread','Interested','Going'],Hidden:['Pass'],Interested:['Interested'],Going:['Going'],All:['Unread','Pass','Interested','Going']};
 function status(row,decisions){return decisions[String(row.id)]||row.status||'Unread';}
 function matches(row,p,limits,decisions,skip=null,ignoreView=false){
  if(!ignoreView&&!(statuses[p.review_view]||statuses['To Review']).includes(status(row,decisions)))return false;
  if(skip!=='venue'&&(p.excluded_venues||[]).includes(row.venue))return false;
  if(skip!=='genre'&&(row.genre_options||['Unknown']).every(g=>(p.excluded_genres||[]).includes(g)))return false;
  if(skip!=='type'&&(p.excluded_types||[]).includes(row.show_type))return false;
  const [low,high]=p.listener_range||[0,limits.listeners];
  if(row.listeners==null){if(p.hide_unknown||low>0)return false;}else if(row.listeners<low*1000||row.listeners>high*1000)return false;
  if(p.growth_range&&(row.growth==null||row.growth<p.growth_range[0]||row.growth>p.growth_range[1]))return false;
  const q=(p.query||'').trim().toLocaleLowerCase();
  if(q&&!(row.search_text||row.name||'').toLocaleLowerCase().includes(q))return false;
  return true;
 }
 function select(rows,p,limits,decisions={}){return rows.filter(r=>matches(r,p,limits,decisions));}
 function counts(rows,p,limits,decisions={}){
  const result={venue:{},genre:{},type:{},totals:{venue:0,genre:0,type:0},views:Object.fromEntries(views.map(v=>[v,0]))};
  for(const row of rows){
   if(matches(row,p,limits,decisions,null,true))for(const v of views)if(statuses[v].includes(status(row,decisions)))result.views[v]++;
   for(const facet of ['venue','genre','type'])if(matches(row,p,limits,decisions,facet)){
    result.totals[facet]++;
    const values=facet==='venue'?[row.venue]:facet==='type'?[row.show_type]:row.genre_options||['Unknown'];
    for(const value of values)result[facet][value]=(result[facet][value]||0)+1;
   }
  }
  return result;
 }
 const model={views,statuses,status,matches,select,counts};
 root.SoundcheckFilters=model;
 if(typeof module!=='undefined')module.exports=model;
})(typeof window!=='undefined'?window:globalThis);
