const assert=require('node:assert/strict');
const f=require('./concert_discovery/filter_controls/client_filters.js');
const rows=[
 {id:'1',venue:'A',genre_options:['Indie','Rock'],show_type:'Live Music',listeners:600000,growth:20,status:'Unread',search_text:'Band One'},
 {id:'2',venue:'A',genre_options:['Indie'],show_type:'Live Music',listeners:800000,growth:-10,status:'Interested',search_text:'Band Two'},
 {id:'3',venue:'B',genre_options:['Unknown'],show_type:'Live Music',listeners:null,growth:null,status:'Going',search_text:'Unknown Band'},
 {id:'4',venue:'B',genre_options:['Rock'],show_type:'Live Music',listeners:1000000,growth:40,status:'Pass',search_text:'Hidden Band'},
 {id:'5',venue:'A',genre_options:['Unknown'],show_type:'Comedy',listeners:null,growth:null,status:'Unread',search_text:'Comic'}
];
const limits={listeners:9700,growth:[-100,400]};
const p={review_view:'To Review',hide_unknown:true,listener_range:[500,9700],excluded_venues:[],excluded_genres:[],excluded_types:['Comedy']};
const ids=(prefs,decisions={})=>f.select(rows,prefs,limits,decisions).map(r=>r.id);
assert.deepEqual(ids(p),['1','2']);
assert.deepEqual(ids({...p,excluded_venues:['A','B']}),[]);
assert.deepEqual(ids({...p,review_view:'All'}),['1','2','4']);
assert.deepEqual(ids({...p,review_view:'Hidden'}),['4']);
assert.deepEqual(ids({...p,review_view:'Interested'}),['2']);
assert.deepEqual(ids({...p,review_view:'Going',listener_range:null,hide_unknown:false}),['3']);
assert.deepEqual(ids({...p,listener_range:null,hide_unknown:false}),['1','2','3']);
assert.deepEqual(ids({...p,growth_range:[0,100]}),['1']);
assert.deepEqual(ids({...p,query:'tWo'}),['2']);
assert.deepEqual(ids({...p,excluded_genres:['Indie']}),['1']); // OR across multiple genres.
assert.deepEqual(ids(p,{'1':'Pass'}),['2']); // Optimistic action affects the current view.
const c=f.counts(rows,p,limits);
assert.deepEqual(c.views,{'To Review':2,Hidden:1,Interested:1,Going:0,All:3});
assert.equal(c.genre.Indie,2);assert.equal(c.genre.Rock,1);assert.equal(c.totals.genre,2);
assert.equal(f.counts(rows,{...p,excluded_venues:['A','B']},limits).venue.A,2); // Facet omits its own restriction.
console.log('Browser filter behavior checks passed');
