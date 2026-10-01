import subprocess
import unittest
from pathlib import Path


class RecoveredTerminalTests(unittest.TestCase):
    def test_current_terminal_only(self):
        source = Path('browser_extension/flow.js').read_text(encoding='utf-8')
        def section(start, end):
            return source[source.index(start):source.index(end, source.index(start))]
        script = section('  function ownedStoryPolicyTerminal(', '  function evaluateFlowPolicyFailure(')
        script += section('  function canRepairRecoveredTerminal(', '  async function recoverFlowPolicy(')
        script += '''
const assert=require('node:assert/strict');
const pkg={mode:'story',job_id:'STORY-X',run_id:'run',shot_index:1,flow_repair:{enabled:true,revise_story:true}};
const location={pathname:'/project/one'};
const terminal={repair_eligible:true,projectPath:location.pathname,failure_code:'FLOW_POLICY_BLOCKED',
 failure_card_fingerprint:'card',policy_failure_category:'face_or_public_figure'};
const monitor={jobId:pkg.job_id,runId:'run',shotIndex:1,readOnlyRecovery:true,resumedCheckpointRunId:'run'};
assert(canRepairRecoveredTerminal(terminal,monitor));
for(const changed of [{readOnlyRecovery:false},{resumedCheckpointRunId:'old'},{runId:'old'},{jobId:'other'},{shotIndex:2}])
 assert(!canRepairRecoveredTerminal(terminal,{...monitor,...changed}));
for(const changed of [{repair_eligible:false},{failure_card_fingerprint:''},{projectPath:'/project/other'},
 {failure_code:'FLOW_SEND_REVIEW'},{policy_failure_category:'unknown'}])
 assert(!canRepairRecoveredTerminal({...terminal,...changed},monitor));
pkg.flow_repair.enabled=false;assert(!canRepairRecoveredTerminal(terminal,monitor));
'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_recovery_handoff_uses_original_provider_without_generate(self):
        source = Path('browser_extension/flow.js').read_text(encoding='utf-8')
        def section(start, end):
            return source[source.index(start):source.index(end, source.index(start))]
        script = section('  function ownedStoryPolicyTerminal(', '  function evaluateFlowPolicyFailure(')
        script += section('  function canRepairRecoveredTerminal(', '  async function readGenerationState(')
        script += '''
const assert=require('node:assert/strict');
let flowRepairBusy=false,readOnlyInspection=true,automationPaused=false,inspectionCommandId='';
const location={pathname:'/project/one'};
let pkg;
const report=async()=>{};
let stored,actions=[];
const chrome={storage:{local:{get:async()=>({smartpostFlowMonitor:stored}),set:async value=>{stored=value.smartpostFlowMonitor;}}},
 runtime:{sendMessage:async message=>{
 if(message.type==='IS_ACTIVE_FLOW_TAB')return {active:true};
 assert.equal(message.type,'FLOW_SCENE_REPAIR');actions.push(message);
 if(message.action==='status')return {ok:true,phase:'missing'};
 assert.equal(message.action,'start_alternative');return {ok:true};
 }}};
(async()=>{
for(const provider of ['chatgpt','gemini']){
 readOnlyInspection=true;actions=[];
 pkg={mode:'story',job_id:'STORY-X',run_id:'run',shot_index:1,image_ai_provider:provider,
 video_prompt:'original',flow_repair:{enabled:true,revise_story:true}};
 const terminal={repair_eligible:true,projectPath:location.pathname,failure_code:'FLOW_POLICY_BLOCKED',
 failure_card_fingerprint:'card',policy_failure_category:'face_or_public_figure',failure_reason:'reason'};
 stored={jobId:pkg.job_id,runId:'run',shotIndex:1,startedAt:123,readOnlyRecovery:true,
 resumedCheckpointRunId:'run',storyPolicyTerminal:terminal};
 assert.equal(await recoverFlowPolicy(terminal,stored),true);
 assert.equal(readOnlyInspection,false);assert.equal(stored.readOnlyRecovery,false);
 assert.deepEqual(actions.map(x=>x.action),['status','start_alternative']);
 assert(actions.every(x=>x.provider===provider));
 assert.equal(actions[1].original_prompt,'original');assert.equal(actions[1].reason,'reason');
}
})().catch(e=>{console.error(e);process.exitCode=1;});
'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
