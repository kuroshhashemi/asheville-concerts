// Shared, interruptible micro-motion. No delayed filtering or persistence.
(function(root){
 const rolls=new WeakMap();
 const reduced=()=>root.matchMedia('(prefers-reduced-motion: reduce)').matches;
 function roll(node,value){
  const target=Number(value),prior=rolls.get(node),formatted=target.toLocaleString('en-US');
  if(prior&&prior.value===target)return;
  if(prior)for(const a of prior.animations)a.cancel();
  const doc=node.ownerDocument,holder=doc.createElement('span'),fresh=doc.createElement('span');
  holder.style.cssText='display:inline-grid;position:relative;overflow:hidden;vertical-align:bottom;height:1.25em;line-height:1.25em;font-variant-numeric:tabular-nums';
  fresh.textContent=formatted;holder.append(fresh);node.replaceChildren(holder);node.dataset.rollValue=String(target);
  const state={value:target,animations:[]};rolls.set(node,state);
  if(!prior||reduced())return;
  const old=doc.createElement('span');old.textContent=prior.value.toLocaleString('en-US');old.setAttribute('aria-hidden','true');old.style.cssText='position:absolute;inset:0';holder.append(old);
  const direction=target>prior.value?1:-1,options={duration:180,easing:'cubic-bezier(.2,.8,.2,1)'};
  const exit=old.animate([{transform:'translateY(0)',opacity:1},{transform:`translateY(${-direction*100}%)`,opacity:0}],options);
  const enter=fresh.animate([{transform:`translateY(${direction*100}%)`,opacity:0},{transform:'translateY(0)',opacity:1}],options);
  state.animations=[exit,enter];exit.onfinish=()=>old.remove();
 }
 function capture(body){
  const map=new Map(),frameTop=root.frameElement?.getBoundingClientRect().top||0,viewport=root.parent.innerHeight;
  for(const row of body.children){const rect=row.getBoundingClientRect(),visible=rect.bottom+frameTop>0&&rect.top+frameTop<viewport;map.set(row.dataset.showId,{row,rect,visible,widths:visible?[...row.cells].map(c=>c.getBoundingClientRect().width):[]});}
  return map;
 }
 function transition(before,body,animate=true){
  if(!animate||reduced())return;
  const ids=new Set(),frameTop=root.frameElement?.getBoundingClientRect().top||0,viewport=root.parent.innerHeight;
  for(const row of body.children){const id=row.dataset.showId;ids.add(id);const old=before.get(id),rect=row.getBoundingClientRect(),visible=rect.bottom+frameTop>0&&rect.top+frameTop<viewport;
   if(!visible&&!old?.visible)continue;
   row.getAnimations().forEach(a=>a.cancel());
   if(old){const delta=old.rect.top-rect.top;if(Math.abs(delta)>1&&Math.abs(delta)<500)row.animate([{transform:`translateY(${delta}px)`},{transform:'translateY(0)'}],{duration:180,easing:'cubic-bezier(.2,.8,.2,1)'});}
   else row.animate([{opacity:0,transform:'translateY(6px)'},{opacity:1,transform:'translateY(0)'}],{duration:160,easing:'ease-out'});
  }
  let ghosts=0;
  for(const [id,old] of before){if(ids.has(id)||!old.visible||ghosts++>=8)continue;
   const doc=body.ownerDocument,box=doc.createElement('div'),table=doc.createElement('table'),tbody=doc.createElement('tbody'),row=old.row.cloneNode(true);
   box.setAttribute('aria-hidden','true');box.inert=true;box.style.cssText=`position:absolute;pointer-events:none;z-index:5;left:${old.rect.left+root.scrollX}px;top:${old.rect.top+root.scrollY}px;width:${old.rect.width}px;`;
   table.style.cssText='width:100%;min-width:0;table-layout:fixed;border-collapse:collapse;background:'+(root.matchMedia('(prefers-color-scheme: dark)').matches?'#202733':'white');
   [...row.cells].forEach((cell,i)=>{cell.style.width=old.widths[i]+'px';});tbody.append(row);table.append(tbody);box.append(table);doc.body.append(box);
   const animation=box.animate([{opacity:.7,transform:'translateX(0)'},{opacity:0,transform:'translateX(8px)'}],{duration:140,easing:'ease-out',fill:'forwards'});
   animation.onfinish=()=>{box.remove();root.dispatchEvent(new Event('soundcheck:motion-finished'));};
  }
 }
 root.SoundcheckMotion={roll,capture,transition};
})(window);
