const fs=require('node:fs');
const assert=require('node:assert/strict');
const {chromium}=require('playwright');

(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.route('**/*',route=>route.abort());
  const html=fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
  await page.setContent(html);
  for(const file of ['styles.css','foundation.css','setup_wizard.css','recovery_wizard.css'])await page.addStyleTag({content:fs.readFileSync(`web_ui/${file}`,'utf8')});
  await page.addScriptTag({content:'const ui={state:{}};const showPage=page=>{window.lastPage=page};'});
  await page.addScriptTag({content:fs.readFileSync('web_ui/setup_wizard.js','utf8')});
  await page.addScriptTag({content:fs.readFileSync('web_ui/recovery_wizard.js','utf8')});
  await page.evaluate(()=>document.querySelector('[data-view=guide]').classList.add('active'));
  await page.evaluate(()=>renderSetupWizard({system:{extension_compatible:true,voice_configured:true,voice_reference_configured:false,subtitle_connected:false}}));
  assert.match(await page.locator('#setup-progress').textContent(),/ตั้งค่าครบ 2 จาก 4 ข้อ/);
  assert.equal(await page.locator('#dashboard-setup-progress').getAttribute('hidden'),null);
  await page.locator('#setup-next').click();await page.locator('#setup-next').click();
  assert.match(await page.locator('#setup-wizard-body').textContent(),/ระบบยังไม่มีข้อมูลยืนยัน/);
  assert.doesNotMatch(await page.locator('#setup-wizard-body').textContent(),/เข้าสู่ระบบ ChatGPT แล้ว/);
  await page.locator('#setup-confirm-web').click();
  assert.match(await page.locator('#setup-wizard-body').textContent(),/ระบบไม่ได้ตรวจ/);
  await page.evaluate(()=>renderSetupWizard({system:{extension_compatible:true,voice_configured:true,voice_reference_configured:true,subtitle_connected:true}}));
  assert.notEqual(await page.locator('#dashboard-setup-progress').getAttribute('hidden'),null);
  await page.evaluate(()=>openRecoveryWizardForRow({queue_id:'Q',error:'SEND_UNCERTAIN receipt=dispatched'}));
  assert.equal(await page.locator('#automation-error-modal').evaluate(node=>node.open),true);
  assert.match(await page.locator('#recovery-wizard-body').textContent(),/ยังไม่รู้ผล/);
  assert.doesNotMatch(await page.locator('#recovery-wizard-body').textContent(),/SEND_UNCERTAIN/);
  await page.locator('#recovery-next').click();await page.locator('#recovery-next').click();
  assert.match(await page.locator('#recovery-wizard-body').textContent(),/ไม่มีปุ่มส่งใหม่/);
  assert.equal(await page.locator('#recovery-wizard-body button').count(),0);
  assert.match(await page.locator('#automation-error-details').textContent(),/SEND_UNCERTAIN/);
  await page.evaluate(()=>openRecoveryWizardForRow({error:'FLOW_CREDIT_EXHAUSTED'}));
  await page.locator('#recovery-next').click();
  assert.match(await page.locator('#recovery-wizard-body').textContent(),/เปลี่ยนบัญชี Google/);
  assert.doesNotMatch(await page.locator('#recovery-wizard-body').textContent(),/ภาพเคลื่อนไหว/);
  assert.deepEqual(errors,[]);
  console.log('Setup/recovery: seven steps, real 2/4 readiness, user-confirmed login, uncertain-send no replay, Flow account only passed');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
