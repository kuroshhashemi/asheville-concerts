const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
let reduce=false;const animations=[];
class Element{
 constructor(){this.children=[];this.style={};this.dataset={};this.attrs={};this.ownerDocument=doc;}
 append(child){this.children.push(child);}replaceChildren(...children){this.children=children;}
 setAttribute(k,v){this.attrs[k]=v;}remove(){this.removed=true;}
 animate(frames,options){const a={frames,options,cancel(){this.cancelled=true;}};animations.push(a);return a;}
}
const doc={createElement(){return new Element();}},window={matchMedia(){return {matches:reduce};}};
vm.runInNewContext(fs.readFileSync('concert_discovery/filter_controls/motion.js','utf8'),{window,WeakMap,Map,Set,Number,Event:function(){}});
const node=new Element(),roll=window.SoundcheckMotion.roll;
roll(node,10);assert.equal(node.dataset.rollValue,'10');assert.equal(animations.length,0);
roll(node,11);assert.equal(node.dataset.rollValue,'11');assert.equal(animations[0].frames[1].transform,'translateY(-100%)');assert.equal(animations[0].options.duration,180);
roll(node,9);assert.equal(node.dataset.rollValue,'9');assert(animations[0].cancelled&&animations[1].cancelled);assert.equal(animations[2].frames[1].transform,'translateY(100%)');
roll(node,9);assert.equal(animations.length,4);
reduce=true;roll(node,12);assert.equal(node.dataset.rollValue,'12');assert.equal(animations.length,4);assert(animations[2].cancelled&&animations[3].cancelled);
console.log('Rolling-counter cancellation, direction and reduced-motion checks passed');
