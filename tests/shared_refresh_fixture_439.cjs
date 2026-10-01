// In-memory Chrome document lifecycle for extracted production controllers.
const fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync('browser_extension/background.js','utf8');
function fn(name){const at=source.search(new RegExp('(?:async )?function '+name+'\\('));if(at<0)throw Error(name);return source.slice(at,source.indexOf('\n}',at)+2);}
function install(c,{delay=0,observeReady=true}={}){
  let documentId='old-document',pending=0;
  const tabs=c.chrome.tabs,oldReload=tabs.reload,oldGet=tabs.get;
  const scripting=c.chrome.scripting||{},oldScript=scripting.executeScript;
  const oldReady=c.waitForAIRefreshReady;
  c.crypto ||=require('node:crypto').webcrypto;
  c.setTimeout=setTimeout;c.clearTimeout=clearTimeout;
  tabs.get=async(...args)=>({status:'complete',...await oldGet(...args)});
  tabs.reload=async(...args)=>{const result=await oldReload(...args);pending=delay;if(!pending)documentId='new-document';return result;};
  scripting.executeScript=async request=>{
    if(request.files)return oldScript?oldScript(request):[];
    const current=documentId;
    if(pending && --pending===0)documentId='new-document';
    return [{frameId:0,documentId:current,result:{ready:true,busy:false,has_media:false,draft:false}}];
  };
  c.chrome.scripting=scripting;
  vm.runInContext(['waitForAIRefreshReady','waitForAIRecoveryOperation','handoffAIRefreshDocument'].map(fn).join('\n'),c);
  if(oldReady && observeReady){const actual=c.waitForAIRefreshReady;c.waitForAIRefreshReady=async(...args)=>{const result=await actual(...args);await oldReady(...args);return result;};}
  return {document:()=>documentId,setDocument:id=>{documentId=id;},fn};
}
module.exports={install,fn,source};
