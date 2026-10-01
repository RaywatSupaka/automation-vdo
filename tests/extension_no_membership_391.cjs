const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const {fixture}=require('./ai_send_acceptance_harness');
(async()=>{
  const background=fs.readFileSync('browser_extension/background.js','utf8');
  const content=fs.readFileSync('browser_extension/chatgpt.js','utf8');
  const popup=fs.readFileSync('browser_extension/popup.js','utf8');
  for(const source of [background,content,popup]){
    assert(!/MEMBERSHIP_(?:AUTHORIZE|STATUS|LOGIN|LOGOUT)|requireMembership|membershipRequest|\/api\/membership\//.test(source));
  }
  // Keep the old random profile storage key for update continuity, not licensing.
  const section=background.slice(background.indexOf('let membershipProfilePromise ='),background.indexOf('let flowDownloadEventPromise ='));
  const storage={};const chrome={storage:{local:{get:async()=>storage,set:async value=>Object.assign(storage,value)}}};
  const ctx=vm.createContext({chrome,Uint8Array,crypto:require('node:crypto').webcrypto});
  vm.runInContext(section,ctx);const identity=await ctx.membershipProfile();assert.match(identity,/^[a-f0-9]{48}$/);
  const restarted=vm.createContext({chrome,Uint8Array,crypto:{getRandomValues:()=>{throw Error('identity must survive update');}}});
  vm.runInContext(section,restarted);assert.equal(await restarted.membershipProfile(),identity);
  // The actual ChatGPT send path still dispatches once if a hypothetical old
  // license responder would deny it. All existing receipt/ownership checks run.
  const f=fixture({membershipDenied:true,acceptAfterSleeps:2});await f.run();f.checkSingleDispatch();
  assert.equal(f.reports.at(-1).step,'ai_send_accepted');
  const cancelled=fixture({membershipDenied:true,cancelDuringPreparation:true});
  await assert.rejects(cancelled.run());assert.equal(cancelled.commands.filter(e=>e.type==='mousePressed').length,0);
  console.log(JSON.stringify({ok:true,cases:8,providerSubmissions:0}));
})().catch(e=>{console.error(e);process.exitCode=1;});
