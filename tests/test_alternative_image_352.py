import os
import subprocess
import unittest
from pathlib import Path
import tempfile
from core.atomic_json import AtomicJsonFile
from core.scene_progress_view import scene_progress_view

ROOT=Path(__file__).resolve().parents[1]


class AlternativeImage352(unittest.TestCase):
    def test_actual_dom_reader(self):
        script=r"""
const fs=require('fs'),assert=require('assert/strict'),{chromium}=require('playwright');
(async()=>{const browser=await chromium.launch({headless:true});try{const page=await browser.newPage();await page.route('https://img/**',route=>route.abort());
const code=fs.readFileSync('browser_extension/chatgpt.js','utf8');
const fn=code.slice(code.indexOf('  function alternativeImageReply('),code.indexOf('  function alternativeEmptyImageProof('));
const adapter=code.slice(code.indexOf('  function chatGPTConversationFrames('),code.indexOf('  function assistantTurns('));
async function run({busy=false,request='new request',result=true,role=false,old=false,loaded=true,extra=false}={}){
 await page.setContent(`<main><article data-testid="conversation-turn-1"><div data-message-author-role="assistant"><img src="https://img/old"></div></article><article data-testid="conversation-turn-2"><div data-message-author-role="user">new request<img src="https://img/source"></div></article>${result?`<article data-testid="conversation-turn-3"><div ${role?'data-message-author-role="assistant"':''}><img src="https://img/${old?'old':'new'}"></div></article>`:''}${extra?'<article data-testid="conversation-turn-4"><div data-message-author-role="user">other request</div></article>':''}</main>`);
 return page.evaluate(({fn,adapter,busy,loaded,request})=>{
 for(const i of document.querySelectorAll('img')){Object.defineProperties(i,{complete:{value:loaded},naturalWidth:{value:941},naturalHeight:{value:1672}});}
 const IS_GEMINI=false,userTurns=()=>[...document.querySelectorAll('[data-message-author-role="user"]')],stopButtonVisible=()=>busy,generatedImageElements=t=>[...t.querySelectorAll('img')],storyImageAssetKey=i=>i.src;
 const motionRequestIsLatestUser=r=>userTurns().at(-1)?.textContent===r;
 return !!eval('(function(){'+adapter+';return '+fn+';})()')(request,['https://img/source']);
 },{fn,adapter,busy,loaded,request});
}
assert.equal(await run(),true);assert.equal(await run({role:true}),true);
for(const opts of [{busy:true},{request:'wrong'},{result:false},{old:true},{loaded:false},{extra:true}])assert.equal(await run(opts),false,JSON.stringify(opts));
assert(!code.slice(code.indexOf("if(record.alternative_stage==='image_sent'){"),code.indexOf("if(record.alternative_stage==='image_saved'){")).includes('generatedImageElements(document)'));
console.log('8 actual-source image reply cases passed');
}finally{await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1});
"""
        result=subprocess.run(['node','-e',script],cwd=ROOT,capture_output=True,text=True,env=os.environ.copy())
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_repair_progress_is_not_video(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)
            AtomicJsonFile(folder/'prompts/scene_pipeline.json').write({'scenes':{'1':{'phase':'video'}}})
            store=AtomicJsonFile(folder/'prompts/flow_replacement.json')
            job={'scene_count':3,'scene_pipeline_version':1}
            for phase in ['requested','image_saved']:
                store.write({'scenes':{'1':{'phase':phase}}})
                result=scene_progress_view(job,folder,True,83)
                self.assertEqual(result['scene_phase'],'repair')
            store.write({'scenes':{'1':{'phase':'ready'}}})
            self.assertEqual(scene_progress_view(job,folder,True,83)['scene_phase'],'video')
