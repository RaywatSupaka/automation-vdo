const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync('browser_extension/background.js','utf8');
const body=source.slice(source.indexOf('async function closeSavedCoverTabs()'),source.indexOf('async function coverBridgeEvent('));
(async()=>{
 for(const mode of ['ready','pending','failure','navigated','shared','rebound','absent']) {
  const key='smartflowCover:one',url='https://chatgpt.com/c/one';
  const state={[key]:{tab_id:1,phase:mode==='pending'?'generating':'ready',cleanup_pending:true,cleanup_url:url}};
  let removed=0;
  if(mode==='shared')state['smartpostFlowTab:J:2']=1;
  const ctx={chrome:{storage:{local:{get:async()=>structuredClone(state),set:async v=>Object.assign(state,v)}},tabs:{
   get:async()=>{if(mode==='absent')throw Error('No tab with id');if(mode==='rebound')state['smartpostAIWebTab:chatgpt:NEW']=1;return {url:mode==='navigated'?'https://chatgpt.com/c/other':url};},
   remove:async()=>{if(mode==='failure')throw Error('browser unavailable');removed++;}
  }}};
  vm.createContext(ctx);vm.runInContext(body,ctx);await ctx.closeSavedCoverTabs();
  assert.equal(removed,mode==='ready'?1:0,mode);
  assert.equal(state[key].cleanup_pending,!['ready','absent'].includes(mode),mode);
  assert.equal(state[key].phase,mode==='pending'?'generating':'ready');
 }
 console.log('cover cleanup: 7 cases passed');
})().catch(e=>{console.error(e);process.exit(1)});
