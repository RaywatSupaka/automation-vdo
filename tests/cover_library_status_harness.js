const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),path=require('path');
const source=fs.readFileSync(path.join(__dirname,'../web_ui/library_view.js'),'utf8');
const start=source.indexOf('    card(item) {'),end=source.indexOf('    decorateDetail(',start);
const c={escapeHtml:s=>String(s??''),formatDuration:()=>'',formatDate:()=>''};
vm.createContext(c);vm.runInContext('var view={'+source.slice(start,end)+'};',c);
for(const phase of ['needs_review','queued','running','cancelled']){
  assert(c.view.card({ai_cover_state:{phase}}).includes('ปก AI ยังไม่สำเร็จ • ภาพที่แสดงเป็นภาพเดิม'));
}
for(const phase of [undefined,'ready'])assert(!c.view.card({ai_cover_state:{phase}}).includes('ปก AI ยังไม่สำเร็จ'));
console.log('cover library states passed');
