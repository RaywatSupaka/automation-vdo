"""Actual mobile debugger adapter lifecycle; no real Chrome or generation."""
import subprocess
import unittest
from pathlib import Path
from core.cancellable_process import hidden_process_kwargs


class FlowMobileLifetimeTests(unittest.TestCase):
    def test_owned_flow_session_survives_actions_and_releases_on_navigation(self):
        code = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const text=fs.readFileSync('browser_extension/background.js','utf8');
const events=[],listeners={};let url='https://flow.google.com/project/test';
const chrome={tabs:{get:async()=>({url}),onRemoved:{addListener:f=>listeners.remove=f},onUpdated:{addListener:f=>listeners.update=f}},
debugger:{onDetach:{addListener:f=>listeners.detach=f},attach:async t=>events.push(['attach',t.tabId]),detach:async t=>events.push(['detach',t.tabId]),sendCommand:async(t,c,p)=>events.push([c,t.tabId,p])}};
const context={chrome};vm.createContext(context);
vm.runInContext(text.slice(text.indexOf('function installFlowMobileDebugger(api)'),text.indexOf('let coverPolling')),context);
(async()=>{
 await vm.runInContext('flowMobileDebugger.pin(1)',context);
 assert.equal(events[1][0],'Emulation.setDeviceMetricsOverride');assert.equal(events[1][2].mobile,true);
 for(let n=0;n<4;n++){await chrome.debugger.attach({tabId:1},'1.3');await chrome.debugger.detach({tabId:1});}
 assert.equal(events.length,2,'upload/send/wait/download must not detach or reattach');
 await chrome.debugger.attach({tabId:2},'1.3');await chrome.debugger.detach({tabId:2});
 assert.deepEqual(events.slice(-2),[['attach',2],['detach',2]],'other tabs unchanged');
 listeners.detach({tabId:1});await chrome.debugger.attach({tabId:1},'1.3');
 assert.equal(events.at(-1)[0],'Emulation.setDeviceMetricsOverride');
 listeners.update(1,{url:'https://chatgpt.com/'});await Promise.resolve();
 assert.deepEqual(events.at(-1),['detach',1]);
 url='https://flow.google.com.attacker.test/project/test';
 await assert.rejects(()=>vm.runInContext('flowMobileDebugger.pin(3)',context),/WRONG_TAB/);
 url='https://gemini.google.com/app';
 await assert.rejects(()=>vm.runInContext('flowMobileDebugger.pin(3)',context),/WRONG_TAB/);
 assert(!events.some(e=>e[0]==='Emulation.clearDeviceMetricsOverride'));
 url='https://flow.google.com/';
 listeners.update(4,{url},{url});listeners.update(4,{status:'loading'},{url});
 await vm.runInContext('flowMobileDebugger.pin(4)',context);
 assert.equal(events.filter(e=>e[0]==='attach'&&e[1]===4).length,1);
 assert.equal(events.at(-1)[0],'Emulation.setDeviceMetricsOverride');
 listeners.update(4,{url:'https://gemini.google.com/app'});
 await Promise.resolve();assert.deepEqual(events.at(-1),['detach',4]);
 console.log('ok');
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', code], cwd=Path(__file__).resolve().parents[1],
                                capture_output=True, text=True, timeout=15,
                                **hidden_process_kwargs())
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_mobile_begins_before_reference_upload(self):
        source = (Path(__file__).resolve().parents[1] / 'browser_extension/flow.js').read_text(encoding='utf-8')
        mobile = source.index("type:'SET_FLOW_MOBILE_VIEW'")
        self.assertLess(mobile, source.index('dropReferenceImage().catch', mobile))
