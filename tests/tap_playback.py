"""Delayed playback taps versus seek gestures; real Chromium mouse/native touch.

Uses only generated WAV. PLAYER_URL can target the existing production site.
No autoplay-policy override: resuming must also work under normal browser policy.
"""
import asyncio, json
from playwright.async_api import async_playwright
from browser import BASE, OUT, load, state
from drag_seek import begin, end, candidate


async def observe(page):
 await page.evaluate('''()=>{
  window.actions={toggles:[],lines:[],plays:0,pauses:0,seeks:0};
  const lp=player.getLyricPlayer(),audio=player.getAudio();
  lp.addEventListener('playback-toggle',()=>actions.toggles.push(performance.now()));
  lp.addEventListener('line-activate',e=>actions.lines.push(e.detail));
  audio.addEventListener('play',()=>actions.plays++);
  audio.addEventListener('pause',()=>actions.pauses++);
  audio.addEventListener('seeking',()=>actions.seeks++);
 }''')


async def reset(page, playing=False):
 await page.evaluate('player.getAudio().pause();player.getLyricPlayer().resetScroll();player.seekAudio(0)')
 await page.wait_for_timeout(500)
 if playing:
  await page.locator('#playPauseBtn').click()
  await page.wait_for_function('!player.getAudio().paused && player.getAudio().currentTime>0.05')
 await page.evaluate('window.actions={toggles:[],lines:[],plays:0,pauses:0,seeks:0}')


async def actions(page):
 return await page.evaluate('actions')


async def point(page, blank=False):
 return await page.evaluate('''blank=>{
  const lp=player.getLyricPlayer(),el=lp.getElement();
  if(!blank){const r=lp.currentLyricLineObjects[1].getElement().getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2};}
  const r=el.getBoundingClientRect();
  for(let y=r.top+12;y<r.bottom-12;y+=12)for(let x=r.right-8;x>r.left;x-=12){
   if(document.elementFromPoint(x,y)===el)return {x,y};
  }
  throw new Error('No transcript whitespace hit target');
 }''', blank)


async def tap(page, p, touch):
 if touch: await page.touchscreen.tap(p['x'],p['y'])
 else: await page.mouse.click(p['x'],p['y'])


async def down(page, p, touch):
 if touch:
  cdp=await page.context.new_cdp_session(page)
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[dict(p,id=0)]})
  return cdp
 await page.mouse.move(p['x'],p['y']);await page.mouse.down()


async def up(page, cdp, cancel=False):
 if cdp:
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchCancel' if cancel else 'touchEnd','touchPoints':[]})
  await cdp.detach()
 else: await page.mouse.up()


async def unchanged(page, playing):
 await page.wait_for_timeout(400)
 a=await actions(page);s=await state(page)
 assert a=={'toggles':[],'lines':[],'plays':0,'pauses':0,'seeks':0},a
 assert s['paused'] != playing,s
 if not playing: assert s['time']==0,s


async def main():
 result={'url':BASE,'cases':{},'page_errors':[]};console_errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  for name,touch in [('mouse',False),('touch',True)]:
   page=await browser.new_page(viewport={'width':1024,'height':768},has_touch=touch,is_mobile=touch)
   page.on('pageerror',lambda e:result['page_errors'].append(str(e)))
   page.on('console',lambda m:console_errors.append(m.text) if m.type=='error' else None)
   await load(page);await observe(page)

   for blank in [False,True]:
    await reset(page);pos=await point(page,blank)
    for paused in [False,True]:
     await tap(page,pos,touch)
     released=await page.evaluate('performance.now()')
     await page.wait_for_timeout(100)
     assert (await state(page))['paused']!=paused
     await page.wait_for_timeout(300)
     s=await state(page);a=await actions(page)
     assert s['paused']==paused and not a['lines'] and a['seeks']==0,(s,a)
     assert a['toggles'][-1]-released>=280,a
    assert len(a['toggles'])==2 and a['plays']==1 and a['pauses']==1,a
    result['cases'][f'{name}_single_{"blank" if blank else "line"}_resume_pause']=a

   for playing in [False,True]:
    await reset(page,playing);pos=await point(page)
    await tap(page,pos,touch);await page.wait_for_timeout(65);await tap(page,pos,touch)
    await page.wait_for_timeout(420)
    a=await actions(page);s=await state(page)
    assert not a['toggles'] and a['lines']==[3000] and a['seeks']==1 and a['plays']==a['pauses']==0,(a,s)
    assert s['paused']!=playing and 3<=s['time']<4,(a,s)
    result['cases'][f'{name}_double_{playing}_seek_only']=True
    # Triple input consumes one double then one delayed single.
    await reset(page,playing);pos=await point(page)
    await tap(page,pos,touch);await tap(page,pos,touch);await tap(page,pos,touch)
    await page.wait_for_timeout(420)
    a=await actions(page);s=await state(page)
    assert len(a['toggles'])==1 and a['lines']==[3000] and a['seeks']==1 and s['paused']==playing,(a,s)
    result['cases'][f'{name}_triple_{playing}_one_pair_one_single']=True

    # A pending single is invalidated when the next gesture becomes a drag.
    await reset(page,playing);pos=await point(page)
    await tap(page,pos,touch)
    g=await begin(page,touch,dy=-100)
    preview=await candidate(page)
    assert preview['seconds'] is not None,preview
    await end(page,g);await page.wait_for_timeout(420)
    a=await actions(page);s=await state(page)
    assert not a['toggles'] and a['lines']==[preview['start']] and a['seeks']==1 and a['plays']==a['pauses']==0,(a,s)
    assert s['paused']!=playing and preview['seconds']<=s['time']<preview['seconds']+1,(preview,s)
    result['cases'][f'{name}_pending_then_drag_{playing}_seek_only']=True

    for kind in ['long_hold','cancel','lost_capture','horizontal_return','outside','blur','resize','delay','mode','lyrics','wheel']:
     print(f'Checking {name} {kind} playing={playing}',flush=True)
     await reset(page,playing);pos=await point(page)
     await tap(page,pos,touch)
     cdp=await down(page,pos,touch)
     if kind=='long_hold':
      await page.wait_for_timeout(550)
      assert not (await actions(page))['toggles']
     elif kind=='cancel':
      if not touch: await page.locator('.speech-lyrics').dispatch_event('pointercancel',{'pointerId':1})
     elif kind=='lost_capture':
      # Process pending capture first; releasing before gotpointercapture is
      # established does not generate a native lostpointercapture event.
      if cdp: await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[dict(pos,x=pos['x']+1,id=0)]})
      else: await page.mouse.move(pos['x']+1,pos['y'])
      await page.evaluate('(()=>{const lp=player.getLyricPlayer();lp.getElement().releasePointerCapture(lp.pointer.id)})()')
      if cdp: await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[dict(pos,x=pos['x']+2,id=0)]})
      else: await page.mouse.move(pos['x']+2,pos['y'])
     elif kind in ['horizontal_return','outside']:
      target=dict(pos,x=pos['x']+80) if kind=='horizontal_return' else dict(pos,x=5)
      if cdp:
       await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[dict(target,id=0)]})
       if kind=='horizontal_return': await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[dict(pos,id=0)]})
      else:
       await page.mouse.move(target['x'],target['y'])
       if kind=='horizontal_return': await page.mouse.move(pos['x'],pos['y'])
     elif kind=='blur': await page.evaluate('window.dispatchEvent(new Event("blur"))')
     elif kind=='resize':
      await page.set_viewport_size({'width':1000,'height':768})
      await page.wait_for_timeout(100)
     elif kind=='delay': await page.evaluate('player.applyLyricDelay(500)')
     elif kind=='mode': await page.evaluate('player.getLyricPlayer().setDragSeekEnabled(false)')
     elif kind=='lyrics': await page.evaluate('(()=>{const lp=player.getLyricPlayer();lp.setLyricLines(lp.getLyricLines())})()')
     elif kind=='wheel': await page.locator('.speech-lyrics').dispatch_event('wheel',{'deltaY':10})
     await up(page,cdp,kind=='cancel' and touch)
     await unchanged(page,playing)
     await page.set_viewport_size({'width':1024,'height':768})
     await page.evaluate('player.applyLyricDelay(0);player.getLyricPlayer().setDragSeekEnabled(true)')
     result['cases'][f'{name}_{kind}_{playing}_no_toggle']=True

   # Cancel pending taps even after release, when no active pointer remains.
   for kind in ['blur','resize','delay','mode','lyrics','wheel','context','dispose']:
    await reset(page);pos=await point(page)
    await tap(page,pos,touch)
    if kind=='blur': await page.evaluate('window.dispatchEvent(new Event("blur"))')
    elif kind=='resize': await page.set_viewport_size({'width':1000,'height':768})
    elif kind=='delay': await page.evaluate('player.applyLyricDelay(500)')
    elif kind=='mode': await page.evaluate('player.getLyricPlayer().setDragSeekEnabled(false)')
    elif kind=='lyrics': await page.evaluate('(()=>{const lp=player.getLyricPlayer();lp.setLyricLines(lp.getLyricLines())})()')
    elif kind=='wheel': await page.locator('.speech-lyrics').dispatch_event('wheel',{'deltaY':10})
    elif kind=='context': await page.evaluate('player.getLyricPlayer().setSeekContext(NaN,0)')
    elif kind=='dispose': await page.evaluate('player.getLyricPlayer().dispose()')
    await unchanged(page,False)
    result['cases'][f'{name}_released_then_{kind}_no_toggle']=True
    await page.set_viewport_size({'width':1024,'height':768})
    if kind=='dispose': await load(page);await observe(page)
    else: await page.evaluate('player.applyLyricDelay(0);player.getLyricPlayer().setDragSeekEnabled(true)')

   if touch:
    for outside in [False,True]:
     await reset(page,True);pos=await point(page)
     await tap(page,pos,touch);cdp=await down(page,pos,touch)
     extra={'x':5 if outside else pos['x']+30,'y':pos['y']+30,'id':1}
     await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[dict(pos,id=0),extra]})
     await up(page,cdp)
     await unchanged(page,True)
     result['cases'][f'touch_multitouch_outside_{outside}_no_toggle']=True

   # Real controls keep their own click behavior and cancel a waiting transcript tap.
   await reset(page);pos=await point(page)
   box=await page.locator('#playPauseBtn').bounding_box()
   control={'x':box['x']+box['width']/2,'y':box['y']+box['height']/2}
   await tap(page,pos,touch)
   # Resolve the hit target before arming the timer so actionability waits do
   # not accidentally turn this into two independent taps >320ms apart.
   await tap(page,control,touch)
   await page.wait_for_timeout(420)
   a=await actions(page)
   assert not a['toggles'] and a['plays']==1 and a['pauses']==0,a
   await page.locator('#playPauseBtn').click();await page.wait_for_timeout(420)
   assert (await state(page))['paused']
   result['cases'][f'{name}_play_control_once']=True

   # Embed controls at the transcript boundary to exercise exclusion beyond the toolbar.
   controls=['<button><span>Control</span></button>','<input type="range" value="0">','<input type="text">','<select><option>Option</option></select>','<textarea></textarea>','<div role="slider" tabindex="0">Slider</div>','<div role="button" tabindex="0">Button</div>','<div contenteditable="true">Edit</div>','<form><span>Form</span></form>','<label><span>Label</span></label>']
   for markup in controls:
    await reset(page)
    await page.evaluate('''html=>{const box=document.createElement('div');box.id='test-control';box.style.cssText='position:absolute;top:100px;left:50px;z-index:999;width:180px;height:60px';box.innerHTML=html;box.firstElementChild.style.cssText='display:block;width:160px;height:50px';player.getLyricPlayer().getElement().appendChild(box);window.controlClicks=0;box.addEventListener('click',()=>controlClicks++)}''',markup)
    loc=page.locator('#test-control > *')
    if touch: await loc.tap()
    else: await loc.click()
    if '<select' in markup: await page.keyboard.press('Escape')
    await unchanged(page,False)
    if 'type="range"' in markup:
     # Native touch ranges emit input/change rather than a compatibility click.
     assert float(await loc.input_value())>0
    elif '<button' in markup or 'role="button"' in markup:
     assert await page.evaluate('controlClicks')>=1,markup
    await page.locator('#test-control').evaluate('e=>e.remove()')
   result['cases'][f'{name}_native_and_aria_controls_excluded']=len(controls)

   # No media: neither a blank tap nor a line tap should attempt audio.play().
   await reset(page)
   await page.evaluate('player.getAudio().removeAttribute("src");player.getAudio().load()')
   await page.wait_for_timeout(100)
   for blank in [False,True]:
    await tap(page,await point(page,blank),touch);await page.wait_for_timeout(420)
   a=await actions(page)
   assert a['plays']==a['pauses']==0 and not a['lines'] and (await state(page))['paused'],a
   assert not await page.evaluate('player.state.isPlaying')
   result['cases'][f'{name}_no_audio_no_play_attempt']=True
   await page.close()
  await browser.close()
 assert not result['page_errors'],result['page_errors']
 assert not any('Playback failed' in e for e in console_errors),console_errors
 result['playback_console_errors']=[e for e in console_errors if 'Playback failed' in e]
 (OUT/'tap-playback-results.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))


if __name__=='__main__': asyncio.run(main())
