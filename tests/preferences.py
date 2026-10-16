"""Preference reload/browser-restart, failures and restored-player interactions.
Synthetic media; Chromium touch simulation is not physical iPad Safari coverage.
"""
import asyncio,json,shutil
from playwright.async_api import async_playwright
from browser import BASE,OUT,load,state
from drag_seek import begin,end,candidate,watch,counts

KEY='amll_speech_preferences_v1'
OLD='amll_speech_background_settings_v1'
POINTS=json.dumps({'width':2,'height':2,'conf':[[0,0,-1,-1,0,0,1,1],[1,1,1,1,0,0,1,1]]},separators=(',',':'))
CONTROLS=[
 ('playbackRate','playbackRate',1.6),('volumeControl','volume',.35),('loopPlay','loopPlay',False),
 ('backgroundStyle','backgroundType','cover'),('roundedCover','roundedCover',100),('coverRotation','coverRotationSpeed',5),
 ('coverStyle','coverStyle','longShadow'),('coverBlurLevel','coverBlurLevel',45),
 ('bgFlowSpeed','backgroundFlowSpeed',0),('bgRenderScale','backgroundRenderScale',.5),('bgFPS','backgroundFPS',24),
 ('bgColorMask','backgroundColorMask',False),('bgMaskColor','backgroundMaskColor','#123456'),('bgMaskOpacity','backgroundMaskOpacity',0),
 ('invertColors','invertColors',True),('dominantColor','manualDominantColor','#112233'),
 ('dominantColorLight','manualDominantColorLight','#ddeeff'),('dominantColorDark','manualDominantColorDark','#223344'),
 ('showTranslatedLyric','showTranslatedLyric',False),('showRomanLyric','showRomanLyric',False),
 ('swapLyricPositions','swapLyricPositions',True),('showbgLyric','showbgLyric',False),('swapDuetsPositions','swapDuetsPositions',True),
 ('advanceLyricTiming','advanceLyricTiming',True),('singleLyrics','singleLyrics',True),('hidePassedLyrics','hidePassedLyrics',True),
 ('enableLyricBlur','enableLyricBlur',False),('enableLyricScale','enableLyricScale',False),('enableLyricSpring','enableLyricSpring',False),
 ('lyricAlignPosition','lyricAlignPosition',.6),('wordFadeWidth','wordFadeWidth',.75),('lyricAlignAnchor','lyricAlignAnchor','bottom'),
 ('springPosYMass','posYSpringMass',1.5),('springPosYDamping','posYSpringDamping',.5),
 ('springPosYStiffness','posYSpringStiffness',140),('springPosYSoft','posYSpringSoft',True),
 ('springScaleMass','scaleSpringMass',2),('springScaleDamping','scaleSpringDamping',.6),
 ('springScaleStiffness','scaleSpringStiffness',130),('springScaleSoft','scaleSpringSoft',True),
 ('bgLowFreqVolume','backgroundLowFreqVolume',.4),('fftDataRangeMin','fftDataRangeMin',80),('fftDataRangeMax','fftDataRangeMax',16000),
 ('enableMarquee','marqueeEnabled',False),('showFPS','showFPS',True),('controlPointCode','controlPointCode',POINTS),
]

async def configure(page,id,value):
 await page.locator('#'+id).evaluate('''(e,value)=>{if(e.type==='checkbox')e.checked=value;else e.value=String(value);
  e.dispatchEvent(new Event('input',{bubbles:true}));e.dispatchEvent(new Event('change',{bubbles:true}));}''',value)

async def ready(page):
 await page.wait_for_function('window.player!==undefined')
 await page.evaluate('player.localRestoreReady')
 await page.wait_for_timeout(300)

async def stored(page):
 return await page.evaluate('(k)=>JSON.parse(localStorage.getItem(k))?.values',KEY)

async def snapshot(page):
 return await page.evaluate('''()=>({rate:player.getAudio().playbackRate,volume:player.getAudio().volume,
  state:player.state,drag:player.getLyricPlayer().isDragSeekEnabled,paused:player.getAudio().paused,
  audio:player.selectedMusicFile?.name,captions:player.selectedLyricFile?.name,
  time:player.getAudio().currentTime,delay:player.state.lyricDelay,playAttempts:window.playAttempts.length,
  writes:window.preferenceWrites.length,status:document.querySelector('#preferencesSaveStatus').textContent,
  phase:document.querySelector('#localSavePanel').dataset.preferencesPhase,
  controls:Object.fromEntries([...document.querySelectorAll('#controlPanel input,#controlPanel select')].map(e=>[e.id,e.type==='checkbox'?e.checked:e.value]))})''')

async def observe(context,results):
 await context.add_init_script('''window.preferenceWrites=[];window.playAttempts=[];
 const set=Storage.prototype.setItem;Storage.prototype.setItem=function(k,v){if(k==='amll_speech_preferences_v1')preferenceWrites.push(v);return set.call(this,k,v)};
 const play=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){playAttempts.push(this.src);return play.call(this)};''')
 context.on('page',lambda page:page.on('pageerror',lambda e:results['page_errors'].append(str(e))))
 context.on('request',lambda r:results['non_read_requests'].append(r.method) if r.method not in ['GET','HEAD'] else None)

async def main():
 results={'cases':{},'page_errors':[],'non_read_requests':[]}
 profile=OUT/'synthetic-preference-profile'
 if profile.exists():shutil.rmtree(profile)
 async with async_playwright() as p:
  options={'executable_path':'/usr/bin/chromium','args':['--no-sandbox','--autoplay-policy=no-user-gesture-required'],
           'viewport':{'width':768,'height':1024},'has_touch':True,'is_mobile':True}
  context=await p.chromium.launch_persistent_context(str(profile),**options)
  await observe(context,results);page=await context.new_page();await load(page)
  assert await stored(page) is None,'Initialization must not persist defaults'
  for id,key,value in CONTROLS:
   await configure(page,id,value*100 if key=='volume' else value)
   saved=await stored(page)
   assert saved[key]==value,(id,key,value,saved)
  await page.locator('#dragSeekMode').tap()
  await page.locator('#timeDisplay').tap()
  saved=await stored(page)
  assert saved['dragSeekEnabled']==False and saved['showRemainingTime']==True,saved
  await configure(page,'backgroundStyle','fluid')
  assert (await stored(page))['invertColors']==False and not (await snapshot(page))['state']['invertColors']
  await configure(page,'backgroundStyle','cover')
  assert (await stored(page))['invertColors']==True and (await snapshot(page))['state']['invertColors']
  await page.evaluate('player.applyLyricDelay(750);player.seekAudio(12.345)')
  await page.wait_for_function('player.localMemory.lastProgress==="12.345:750"')
  expected=await stored(page)
  await page.reload();await ready(page)
  restored=await snapshot(page)
  assert await stored(page)==expected
  assert restored['writes']==0 and restored['playAttempts']==0,restored
  assert restored['paused'] and abs(restored['time']-12.345)<.01 and restored['delay']==750,restored
  assert restored['audio']=='synthetic.wav' and restored['captions']=='synthetic.srt',restored
  for id,key,value in CONTROLS:
   actual=restored['rate'] if key=='playbackRate' else restored['volume'] if key=='volume' else restored['controls'][id] if key=='controlPointCode' else restored['state'][key]
   assert actual==value,(id,actual,value)
   ui=restored['controls'][id]
   if isinstance(value,bool):assert ui==value,(id,ui,value)
   elif isinstance(value,(int,float)):assert abs(float(ui)-(value*100 if key=='volume' else value))<.001,(id,ui,value)
   else:assert ui==value,(id,ui,value)
  assert restored['drag']==False and restored['state']['showRemainingTime']==True
  results['cases']['all_controls_autosave_reload_no_initial_overwrite']={'controls':len(CONTROLS)+2,'preference_fields':len(expected),'paused_media_position_delay_restored':True}
  await context.close()
  context=await p.chromium.launch_persistent_context(str(profile),**options)
  await observe(context,results);page=await context.new_page();await page.goto(BASE);await ready(page)
  restarted=await snapshot(page)
  assert await stored(page)==expected and restarted['rate']==1.6 and restarted['volume']==.35
  assert restarted['paused'] and restarted['playAttempts']==0 and abs(restarted['time']-12.345)<.01
  results['cases']['browser_restart_restores_settings_and_complete_media_paused']=True
  # Restore a useful practice layout through the actual controls, then reload it.
  for id,value in [('showFPS',False),('coverStyle','normal'),('coverRotation',0),('swapDuetsPositions',False),
                   ('singleLyrics',False),('hidePassedLyrics',False),('advanceLyricTiming',False),('enableLyricSpring',True),
                   ('lyricAlignAnchor','center'),('lyricAlignPosition',.4),('playbackRate',1.2)]:await configure(page,id,value)
  await page.locator('#dragSeekMode').tap();await page.reload();await ready(page)
  await page.evaluate('player.seekAudio(4.5)');await page.wait_for_timeout(600);await watch(page)
  lp=page.locator('[aria-label^="Seek to Synthetic sentence 2."]')
  await lp.tap();box=await lp.bounding_box();await page.touchscreen.tap(box['x']+box['width']/2,box['y']+box['height']/2)
  await page.wait_for_timeout(250)
  assert await counts(page)=={'commits':[3000],'seeks':1}
  assert abs((await state(page))['time']-2.25)<.01 and (await state(page))['paused']
  await page.evaluate('player.seekAudio(3.75)');await page.wait_for_timeout(600)
  await page.evaluate('window.commits=[];window.seeks=0')
  g=await begin(page,True,dy=18,start_fraction=.5)
  delta=await page.evaluate('(()=>{const p=player.getLyricPlayer(),l=p.currentLyricLineObjects[1];return p.size[1]/2-p.targetTop.get(l)-p.lyricLinesSize.get(l)[1]/2})()')
  await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':g['x'],'y':g['y']+delta,'id':0}]})
  await page.wait_for_timeout(100);c=await candidate(page);assert c['start']==3000,c
  await end(page,g);assert await counts(page)=={'commits':[3000],'seeks':1}
  assert abs((await state(page))['time']-2.25)<.01 and (await state(page))['paused']
  await page.reload();await ready(page);assert abs((await state(page))['time']-2.25)<.01
  results['cases']['restored_double_tap_and_same_sentence_drag_save_position']=True
  for name,w,h in [('phone',390,844),('phone-landscape',844,390),('tablet',1024,768)]:
   await page.set_viewport_size({'width':w,'height':h});await page.wait_for_timeout(400)
   await page.locator('#localSavePanel').evaluate('e=>e.open=true')
   info=await page.locator('#localSavePanel .save-details').evaluate('e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,right:r.right,bottom:r.bottom,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}}')
   assert info['x']>=0 and info['right']<=w and info['bottom']<=h and info['scrollWidth']<=info['clientWidth'],(name,info)
   await page.screenshot(path=str(OUT/f'preferences-{name}.png'))
   await page.locator('#localSavePanel').evaluate('e=>e.open=false')
  results['cases']['existing_glass_save_panel_mobile_bounds']=True
  # Explicit URL choices apply to this visit, without overwriting saved defaults.
  before_url=await stored(page)
  await page.goto(BASE+'?x=1.8&vol=25&loop=0&auto=0');await ready(page)
  s=await snapshot(page)
  assert s['rate']==1.8 and s['volume']==.25 and not s['state']['loopPlay'] and s['paused'],s
  assert await stored(page)==before_url and s['writes']==0
  await page.goto(BASE);await ready(page);assert (await snapshot(page))['rate']==1.2
  results['cases']['url_override_is_visit_only_and_survives_media_restore']=True
  # An old position at/past EOF must not trigger the restored repeat preference.
  await configure(page,'loopPlay',True)
  for extra in [0,5]:
   await page.evaluate('''async extra=>{player.restoringLocal=true;
    const saved=await player.localMemory.backend.read();
    saved.progress.position=player.getAudio().duration+extra;saved.progress.updatedAt=Date.now()+60000;
    await player.localMemory.backend.write(saved);
   }''',extra)
   await page.reload();await ready(page);await page.wait_for_timeout(400)
   s=await snapshot(page)
   assert s['paused'] and s['playAttempts']==0 and s['time']==60,(extra,s)
  await configure(page,'loopPlay',False)
  results['cases']['end_position_restores_paused_even_with_repeat_enabled']=True
  await page.locator('#localSavePanel summary').click();await page.locator('#clearLocalSession').click()
  await page.wait_for_function('document.querySelector("#localSavePanel").dataset.phase==="cleared"')
  await page.reload();await ready(page)
  assert not (await snapshot(page)).get('audio') and await stored(page)==before_url
  await page.evaluate('document.getElementById("resetPlayer").click()')
  await page.reload();await ready(page);s=await snapshot(page)
  assert s['rate']==1 and s['volume']==.5 and s['drag'] and s['state']['showRomanLyric'],s
  results['cases']['clear_files_keeps_preferences_and_reset_restores_defaults']=True
  await context.close()
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  async def seeded(data):
   ctx=await browser.new_context();await observe(ctx,results);pg=await ctx.new_page();await pg.goto(BASE);await ready(pg)
   await pg.evaluate('(data)=>{localStorage.clear();for(const [k,v] of Object.entries(data))localStorage.setItem(k,v)}',data)
   await pg.reload();await ready(pg)
   return ctx,pg
  ctx,pg=await seeded({OLD:json.dumps({'backgroundFlowSpeed':0,'showRomanLyric':False,'lyricAlignAnchor':'top','backgroundFPS':19}), 'amll_speech_drag_seek_v1':'false'})
  s=await snapshot(pg);assert s['writes']==0 and s['state']['backgroundFlowSpeed']==0 and not s['state']['showRomanLyric'] and not s['drag'],s
  assert s['controls']['lyricAlignAnchor']=='top' and s['controls']['bgFPS']=='19'
  await configure(pg,'volumeControl',0);assert (await stored(pg))['volume']==0 and not (await stored(pg))['dragSeekEnabled']
  results['cases']['legacy_migration_zero_false_and_first_edit']=True;await ctx.close()
  bad={'version':1,'values':{'playbackRate':999,'volume':-2,'backgroundType':'invalid','showRomanLyric':'false','backgroundFPS':'20',
       'manualDominantColor':'url(bad)','fftDataRangeMin':1000,'fftDataRangeMax':1,'controlPointCode':'{"width":999999}', 'loopPlay':False}}
  ctx,pg=await seeded({KEY:json.dumps(bad)});s=await snapshot(pg)
  assert s['rate']==1 and s['volume']==.5 and s['state']['backgroundType']=='fluid' and s['state']['showRomanLyric']==True and s['state']['loopPlay']==False,s
  assert s['phase']=='error' and s['writes']==0
  await configure(pg,'playbackRate',1.3);await pg.reload();await ready(pg);assert (await snapshot(pg))['rate']==1.3
  results['cases']['invalid_fields_keep_valid_values_and_recover']=True;await ctx.close()
  for text in ['{bad',json.dumps({'version':2,'values':{'volume':.1}})]:
   ctx,pg=await seeded({KEY:text});s=await snapshot(pg);assert s['phase']=='error' and s['writes']==0
   await configure(pg,'playbackRate',1.4)
   if text=='{bad':assert (await stored(pg))['playbackRate']==1.4
   else:assert await pg.evaluate('(k)=>localStorage.getItem(k)',KEY)==text
   await ctx.close()
  results['cases']['corrupt_json_recovery_and_future_schema_preservation']=True
  ctx,pg=await seeded({KEY:json.dumps({'version':1,'values':{'playbackRate':1.6}})})
  await pg.evaluate('''()=>{const set=Storage.prototype.setItem;window.allowPreferenceWrites=false;
   Storage.prototype.setItem=function(k,v){if(k==='amll_speech_preferences_v1'&&!allowPreferenceWrites)throw new DOMException('quota','QuotaExceededError');return set.call(this,k,v)};}''')
  await configure(pg,'playbackRate',.8);s=await snapshot(pg);assert s['rate']==.8 and s['phase']=='error' and (await stored(pg))['playbackRate']==1.6
  await pg.evaluate('window.allowPreferenceWrites=true');await configure(pg,'playbackRate',1.1);assert (await snapshot(pg))['phase']=='saved'
  await pg.reload();await ready(pg);assert (await snapshot(pg))['rate']==1.1
  results['cases']['quota_keeps_previous_record_and_next_change_retries']=True;await ctx.close()
  ctx=await browser.new_context();await observe(ctx,results)
  await ctx.add_init_script("Object.defineProperty(window,'localStorage',{get(){throw new DOMException('blocked','SecurityError')}})")
  pg=await ctx.new_page();await pg.goto(BASE);await ready(pg);await configure(pg,'playbackRate',1.4)
  assert (await snapshot(pg))['rate']==1.4 and (await snapshot(pg))['phase']=='error'
  await pg.evaluate('player.resetPlayer()');assert (await snapshot(pg))['rate']==1
  results['cases']['unavailable_storage_keeps_player_usable']=True;await ctx.close()
  await browser.close()
 assert not results['page_errors'],results['page_errors']
 assert not results['non_read_requests'],results['non_read_requests']
 results['limits']='Local production build, Chromium desktop/touch and persistent-profile restart; no physical iPad Safari.'
 (OUT/'preferences-results.json').write_text(json.dumps(results,indent=2))
 print(json.dumps(results,indent=2))

if __name__=='__main__':asyncio.run(main())
