const assert=require('node:assert/strict');
const fs=require('node:fs');
const {chromium}=require('playwright');
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.SMARTFLOW_TEST_CHROMIUM?{executablePath:process.env.SMARTFLOW_TEST_CHROMIUM}:{})});
  const outputs=[];let checks=0;
  try{
    const page=await browser.newPage({viewport:{width:960,height:900}}),errors=[];
    page.on('pageerror',error=>errors.push(error.message));
    await page.route('**/*',route=>route.abort());
    await page.setContent(`<label><select id="product-video-provider"><option value="flow">Flow</option></select></label>
      <label><select id="story-video-mode"><option value="google_flow">Flow</option><option value="image_motion">Local</option></select></label>
      <label><select id="story-batch-video-mode"><option value="meta_ai">Meta</option></select></label>
      <label><select id="drama-video-mode"><option value="meta_ai">Meta</option></select></label>
      <label><select id="long-mode"><option value="meta_ai">Meta</option></select></label>
      <section id="creation-form"><div class="cq-buttons"></div></section>`);
    await page.addScriptTag({content:`const calls=[];let postAction=async(action,payload)=>{calls.push({action,payload});return {ok:true}};`});
    await page.addScriptTag({content:fs.readFileSync('web_ui/media_audio.js','utf8')});
    for(const [key,action,payload] of [
      ['product','create_product',{video_provider:'flow'}],
      ['story','create_story',{video_generation_mode:'google_flow'}],
      ['story-batch','enqueue_story_batch',{video_generation_mode:'meta_ai'}],
      ['drama','create_drama_series',{render_options:{video_generation_mode:'meta_ai'}}],
      ['long','create_story',{long_video:{version:2},video_generation_mode:'meta_ai'}],
      ['product-batch','creation_enqueue',{mode:'product',video_generation_mode:'google_flow'}],
    ]){
      const area=page.locator(`[data-audio-form="${key}"]`);
      assert.equal(await area.locator('[data-generated-music-enabled]').isChecked(),false);checks++;
      await area.locator('.audio-generated-music summary').click();
      await area.locator('[data-generated-music-enabled]').check();
      await area.locator('[data-generated-music-mood]').selectOption('warm');
      const saved=await page.evaluate(async({key,action,payload})=>{
        await postAction(action,payload);return calls.at(-1).payload;
      },{key,action,payload});
      assert.equal(saved.generated_music_options.enabled,true);
      assert.equal(saved.generated_music_options.mood,'warm');
      assert.equal(saved.audio_choices.keep_video_audio,true);
      assert.equal(saved.audio_choices.generated_music_version,1);checks+=4;
      if(key==='drama')assert.deepEqual(saved.render_options.generated_music_options,saved.generated_music_options);
      outputs.push({key,payload:saved});
      await area.locator('[data-generated-music-enabled]').uncheck();
      const disabled=await page.evaluate(key=>({music:generatedMusicChoice(key),audio:mediaAudioChoice(key)}),key);
      assert.equal(disabled.audio.keep_video_audio,false);
      assert.equal('generated_music_version' in disabled.audio,false);checks+=2;
    }
    await page.evaluate(()=>{
      setGeneratedMusicChoice('story',{version:1,enabled:true,mood:'warm',frequency:'moderate'});
      setMediaAudioChoice('story',{mode:'api',keep_video_audio:true,music:true});
    });
    let message=await page.evaluate(async()=>{try{await postAction('create_story',{video_generation_mode:'google_flow'});return '';}catch(e){return e.message;}});
    assert.match(message,/ดนตรี AI/);checks++;
    await page.evaluate(()=>setMediaAudioChoice('story',{mode:'none',music:false}));
    message=await page.evaluate(async()=>{try{await postAction('create_story',{video_generation_mode:'google_flow'});return '';}catch(e){return e.message;}});
    assert.match(message,/ดนตรี AI/);checks++;
    await page.evaluate(()=>{setGeneratedMusicChoice('story',null);document.querySelector('#story-video-mode').value='image_motion';refreshMediaAudio('story');});
    assert.equal(await page.locator('[data-audio-form="story"] [data-generated-music-enabled]').isDisabled(),true);checks++;
    await page.evaluate(()=>prepareAudioQueue({video_generation_mode:'meta_ai',settings:{audio_choices:{mode:'flow_original'},generated_music_options:{version:1,enabled:true,mood:'tender',frequency:'sparse'}}}));
    assert.equal((await page.evaluate(()=>generatedMusicChoice('product-batch'))).mood,'tender');checks++;
    await page.evaluate(()=>prepareAudioQueue({video_generation_mode:'meta_ai',settings:{audio_choices:{mode:'flow_original'}}}));
    assert.equal((await page.evaluate(()=>generatedMusicChoice('product-batch'))).enabled,false);checks++;
    // Frozen Product handoff never recaptures today's controls.
    await page.evaluate(()=>{window.productOptionSnapshot={isFrozen:p=>!!p.product_option_snapshot};setGeneratedMusicChoice('product',{version:1,enabled:true,mood:'bright'});});
    const frozen=await page.evaluate(async()=>{await postAction('create_product',{product_option_snapshot:{version:1},generated_music_options:{version:1,enabled:false}});return calls.at(-1).payload;});
    assert.equal(frozen.generated_music_options.enabled,false);checks++;
    assert.deepEqual(errors,[]);
    console.log('BACKEND_MUSIC='+JSON.stringify(outputs));
    console.log(`PASS generated music native UI ${checks} checks / 6 forms`);
  }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
