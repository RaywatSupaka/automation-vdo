const fs=require('fs'), assert=require('node:assert/strict'), vm=require('vm');
const {chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,channel:'msedge'});
  try {
    const page=await browser.newPage(); const errors=[];
    page.on('pageerror',e=>errors.push(e.message));
    const html=fs.readFileSync('web_ui/index.html','utf8').replace(/<script\b[^>]*>[\s\S]*?<\/script>/gi,'').replace(/<link\b[^>]*>/gi,'');
    await page.setContent(html);
    await page.evaluate(()=>{
      document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.dataset.view==='products'));
      window.calls=[];window.postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true};};
      const f=document.createElement('form');f.id='creation-form';f.innerHTML='<div class="cq-buttons"></div>';document.body.append(f);
    });
    for(const file of ['styles.css','workspace.css','media_audio.css'])await page.addStyleTag({path:'web_ui/'+file});
    await page.addScriptTag({path:'web_ui/media_audio.js'});
    const panel=page.locator('[data-view="products"] .media-audio-controls');
    await panel.locator('[data-audio-mode][value="flow_original"]').check();
    assert.equal(await page.evaluate(()=>mediaAudioChoice('product').mode),'flow_original');
    assert.equal(await page.evaluate(()=>mediaAudioChoice('product').video_audio_volume),100);
    assert.match(await panel.locator('[data-subtitle-source]').innerText(),/เสียงจริง/);
    await panel.locator('[data-audio-mode][value="api"]').check();
    await panel.locator('summary').click();
    await panel.locator('[data-audio-keep]').check();
    await panel.locator('[data-audio-music]').check();
    await panel.locator('[data-audio-sfx]').check();
    await panel.locator('[data-audio-mode][value="flow_original"]').check();
    await page.evaluate(()=>postAction('create_product',{}));
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.keep_video_audio),false);
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.music),true);
    await panel.locator('[data-audio-mode][value="api"]').check();
    assert.equal(await panel.locator('[data-audio-keep]').isChecked(),true);
    await panel.locator('[data-audio-subtitle]').uncheck();
    assert.match(await panel.locator('[data-subtitle-source]').innerText(),/ไม่เรียกบริการ/);
    await panel.locator('[data-audio-keep]').uncheck();
    await page.locator('#product-video-provider').selectOption('meta_ai');
    assert.equal(await panel.locator('[data-audio-mode][value="flow_original"]').isEnabled(),true);
    await panel.locator('[data-audio-mode][value="flow_original"]').check();
    await page.evaluate(()=>postAction('create_product',{video_provider:'meta_ai'}));
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.mode),'flow_original');
    assert.match(await panel.locator('[data-audio-capability]').innerText(),/Meta AI/);
    await page.evaluate(()=>prepareAudioQueue({video_generation_mode:'meta_ai',settings:{audio_choices:{mode:'flow_original',subtitle:false,video_audio_volume:73}}}));
    assert.equal(await page.locator('#creation-form .cq-buttons').count(),1);
    const queuePanel=page.locator('#creation-form .media-audio-controls');
    assert.equal(await queuePanel.locator('[data-audio-mode][value="flow_original"]').isEnabled(),true);
    await page.evaluate(()=>postAction('creation_edit',{video_generation_mode:'meta_ai'}));
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.mode),'flow_original');
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.video_audio_volume),73);
    await page.evaluate(()=>{const s=document.querySelector('#story-video-mode');s.value='meta_ai';s.dispatchEvent(new Event('change'));});
    await page.evaluate(()=>{
      const panel=document.querySelector('#story-video-mode').closest('label').nextElementSibling;
      panel.querySelector('[data-audio-mode][value="flow_original"]').click();
    });
    await page.evaluate(()=>postAction('create_story',{video_generation_mode:'meta_ai'}));
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.mode),'flow_original');
    await page.evaluate(()=>{const s=document.querySelector('#story-video-mode');s.value='image_motion';s.dispatchEvent(new Event('change'));});
    assert.equal(await page.evaluate(()=>document.querySelector('#story-video-mode').closest('label').nextElementSibling.querySelector('[data-audio-mode][value="flow_original"]').disabled),true);
    await page.evaluate(()=>{
      const s=document.querySelector('#story-video-mode');s.value='meta_ai';s.dispatchEvent(new Event('change'));
      const p=s.closest('label').nextElementSibling;
      p.querySelector('[data-audio-mode][value="api"]').click();
      p.querySelector('[data-actor-dialogue]').click();
    });
    await page.evaluate(()=>postAction('create_story',{video_generation_mode:'meta_ai'}));
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.actor_dialogue),true);
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.subtitle),false);
    assert.equal(await page.evaluate(()=>document.querySelector('#story-video-mode').closest('label').nextElementSibling.querySelector('[data-audio-subtitle]').disabled),true);
    for(const provider of ['google_flow','meta_ai']){
      await page.evaluate(provider=>{document.querySelector('#story-batch-video-mode').value=provider;prepareStoryAudioBatch();},provider);
      await page.evaluate(provider=>postAction('enqueue_story_batch',{video_generation_mode:provider}),provider);
      assert.equal(await page.evaluate(()=>calls.at(-1).payload.actor_dialogue),true);
      assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.subtitle),false);
    }
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.mode),'flow_original');
    assert.equal(await page.evaluate(()=>document.querySelector('#story-video-mode').closest('label').nextElementSibling.querySelector('[data-audio-mode][value="api"]').disabled),true);
    await page.evaluate(()=>document.querySelector('#story-video-mode').closest('label').nextElementSibling.querySelector('[data-actor-dialogue]').click());
    assert.equal(await page.evaluate(()=>mediaAudioChoice('story').mode),'api');
    await page.evaluate(()=>postAction('create_story',{video_generation_mode:'meta_ai'}));
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.actor_dialogue),false);
    await page.evaluate(()=>prepareStoryAudioBatch());
    await page.evaluate(()=>postAction('enqueue_story_batch',{video_generation_mode:'meta_ai'}));
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.actor_dialogue),false);
    assert.equal(await page.evaluate(()=>calls.at(-1).payload.audio_choices.mode),'api');
    await page.evaluate(()=>postAction('create_product',{job_id:'OLD'}));
    assert.equal(await page.evaluate(()=>Object.hasOwn(calls.at(-1).payload,'audio_choices')),false);
    assert.equal(await panel.locator('button[data-page="subtitle"]').count(),1);
    assert.equal(await panel.locator('button[data-page="voice"]').count(),1);
    // Render real HTML/CSS, not a mock UI; no localhost/provider requests.
    fs.mkdirSync('docs/reports/audio-ui-v2',{recursive:true});
    for(const width of [1400,900,600,360]){
      await page.setViewportSize({width,height:1000});
      await panel.screenshot({path:`docs/reports/audio-ui-v2/controls-${width}.png`});
      assert.equal(await panel.evaluate(n=>n.scrollWidth<=n.clientWidth+2),true);
    }
    await page.evaluate(()=>{
      document.querySelectorAll('.page').forEach(p=>p.classList.remove('active'));
      const s=document.querySelector('#story-video-mode');s.closest('.page').classList.add('active');
      s.closest('label').nextElementSibling.querySelector('[data-actor-dialogue]').click();
    });
    const storyPanel=page.locator('#story-video-mode').locator('..').locator('xpath=following-sibling::fieldset[1]');
    for(const width of [600,360]){
      await page.setViewportSize({width,height:1000});
      await storyPanel.screenshot({path:`docs/reports/audio-ui-v2/actors-${width}.png`});
      assert.equal(await storyPanel.evaluate(n=>n.scrollWidth<=n.clientWidth+2),true);
    }
    const code=fs.readFileSync('web_ui/app.js','utf8');
    const func=code.slice(code.indexOf('function progressSteps('),code.indexOf('function minimizeProgress('));
    const ctx={};vm.createContext(ctx);vm.runInContext(func,ctx);
    const steps=ctx.progressSteps('story',72,{pipeline_phase:'voice',audio_mode:'api'});
    assert.match(steps,/current">เสียง SmartSub/);
    assert.doesNotMatch(steps,/สร้างวิดีโอ/); // image-motion has no provider-video phase
    const nativeSteps=ctx.progressSteps('story',61,{pipeline_phase:'source_video',audio_mode:'flow_original'});
    assert.doesNotMatch(nativeSteps,/เสียง SmartSub/);
    assert.match(nativeSteps,/current">สร้างวิดีโอ/);
    assert.deepEqual(errors,[]);
    console.log('PASS audio cards: Meta native product/story/queue, image-motion gate, native100, preserved music/SFX, saved-job resume, settings links, 4 widths and owned phase labels');
  } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
