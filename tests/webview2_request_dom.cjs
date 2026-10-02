const assert = require('node:assert/strict');
const {spawnSync} = require('node:child_process');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const python = path.join(root, '.venv', 'Scripts', 'python.exe');
const source = `import json
from desktop.webview2_request import PREFLIGHT,prepare_script,ready_script,click_script,observe_script
p='เล่าเรื่องสั้นเกี่ยวกับดาวดวงหนึ่ง'
u='https://chatgpt.com/'
print(json.dumps({'preflight':PREFLIGHT,'prepare':prepare_script(p),'ready':ready_script(p,0,u),'click':click_script(p,0,u),'observe':observe_script(p)}))`;
const generated = spawnSync(python, ['-c', source], {cwd:root, encoding:'utf8'});
if (generated.status !== 0) throw Error(generated.stderr || 'Could not compile WebView2 scripts');
const scripts = JSON.parse(generated.stdout);

const users = [], assistants = [];
const visible = () => ({width:300,height:50});
const editor = {tagName:'DIV',innerText:'',getBoundingClientRect:visible,
  focus(){},dispatchEvent(){}};
const send = {disabled:false,getAttribute(){return null},getBoundingClientRect:visible,
  click(){users.push({innerText:editor.innerText,getBoundingClientRect:visible});
    assistants.push({innerText:'คำตอบทดลอง',getBoundingClientRect:visible});
    editor.innerText='';}};
const selection = {removeAllRanges(){},addRange(){}};
const context = {
  location:{origin:'https://chatgpt.com',href:'https://chatgpt.com/'},
  document:{readyState:'complete',querySelectorAll(selector){
    if(selector.includes('#prompt-textarea'))return [editor];
    if(selector.includes('send-button'))return [send];
    if(selector.includes('data-message-author-role="user"'))return users;
    if(selector.includes('data-message-author-role="assistant"'))return assistants;
    return [];
  },createRange(){return {selectNodeContents(){}}},
  execCommand(command,_ui,value){if(command==='insertText'){editor.innerText=value;return true}return false}},
  window:{getSelection(){return selection}},
  getComputedStyle(){return {display:'block',visibility:'visible'}},
  Event:class{},InputEvent:class{},
};
const evaluate = script => vm.runInNewContext(script,context);
assert.equal(evaluate(scripts.preflight).composer_count,1);
assert.equal(evaluate(scripts.preflight).draft_length,0);
assert.equal(evaluate(scripts.prepare).ok,true);
assert.equal(evaluate(scripts.ready).ok,true);
assert.equal(evaluate(scripts.click).clicked,true);
const result=evaluate(scripts.observe);
assert.equal(result.latest_user_matches,true);
assert.equal(result.user_count,1);
assert.equal(result.assistant_text,'คำตอบทดลอง');
assert.equal(evaluate(scripts.click).clicked,false);
console.log('WebView2 request DOM fixture: one send, owned response, no repeated send');
