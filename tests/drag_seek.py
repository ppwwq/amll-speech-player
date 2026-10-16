"""Drag-to-seek regression with real Chromium mouse/CDP touch; no physical iPad claim."""
import asyncio,json
from playwright.async_api import async_playwright
from browser import load,state,srt,OUT,BASE

async def reset(page,time=0,delay=0):
 await page.evaluate('''({time,delay})=>{player.getAudio().pause();player.exitRangeMode();player.applyLyricDelay(delay);player.getLyricPlayer().resetScroll();player.seekAudio(time)}''',{'time':time,'delay':delay})
 await page.wait_for_timeout(600)
 await page.evaluate('window.commits=[];window.seeks=0')

async def watch(page):
 await page.evaluate('''()=>{window.commits=[];window.seeks=0;player.getLyricPlayer().addEventListener('line-activate',e=>commits.push(e.detail));player.getAudio().addEventListener('seeking',()=>seeks++)}''')

async def candidate(page):
 return await page.locator('.drag-seek-guide').evaluate('''e=>({visible:!e.hidden,start:e.dataset.startMs===undefined?null:Number(e.dataset.startMs),seconds:e.dataset.audioSeconds===undefined?null:Number(e.dataset.audioSeconds),label:e.textContent})''')

async def counts(page):
 return await page.evaluate('({commits:window.commits,seeks:window.seeks})')

async def begin(page,touch=False,dy=-180,start_fraction=.7):
 b=await page.locator('.speech-lyrics').bounding_box()
 x=b['x']+b['width']/2;y=b['y']+b['height']*start_fraction
 cdp=await page.context.new_cdp_session(page) if touch else None
 if cdp: await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0}]})
 else: await page.mouse.move(x,y);await page.mouse.down()
 for i in range(1,9):
  if cdp: await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y+dy*i/8,'id':0}]})
  else: await page.mouse.move(x,y+dy*i/8)
  await page.wait_for_timeout(20)
 await page.wait_for_timeout(120)
 return {'cdp':cdp,'x':x,'y':y+dy,'box':b}

async def end(page,g,cancel=False):
 if g['cdp']:
  await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchCancel' if cancel else 'touchEnd','touchPoints':[]})
  await g['cdp'].detach()
 else: await page.mouse.up()
 await page.wait_for_timeout(200)

async def no_commit(page):
 c=await counts(page);assert c['commits']==[] and c['seeks']==0,c

async def main():
 results={};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  desktop=await browser.new_page(viewport={'width':1280,'height':900})
  desktop.on('pageerror',lambda e: errors.append(str(e)))
  await load(desktop);await watch(desktop);await reset(desktop)
  assert await desktop.locator('#dragSeekMode').get_attribute('aria-pressed')=='true'
  g=await begin(desktop)
  before=await candidate(desktop)
  assert before['visible'] and before['seconds'] is not None and before['seconds']>0,before
  assert (await state(desktop))['time']==0
  await no_commit(desktop)
  # The marked sentence is also the one nearest the drawn centre guide, not just model state.
  geometry=await desktop.evaluate('''()=>{let lp=player.getLyricPlayer();const guide=lp.getElement().querySelector('.drag-seek-guide').getBoundingClientRect();const lines=[...lp.getElement().querySelectorAll('[role=button]')].map(e=>({selected:e.hasAttribute('data-drag-candidate'),distance:Math.abs(e.getBoundingClientRect().y+e.getBoundingClientRect().height/2-guide.y)}));lines.sort((a,b)=>a.distance-b.distance);return lines[0]}''')
  assert geometry['selected'],geometry
  await desktop.screenshot(path=str(OUT/'drag-seek-desktop.png'))
  await end(desktop,g)
  st=await state(desktop);c=await counts(desktop)
  assert abs(st['time']-before['seconds'])<.01 and st['paused'] and not st['following'],(st,before)
  assert c['commits']==[before['start']] and c['seeks']==1,c
  assert int(before['start']/3000) in st['hot'],st
  await desktop.wait_for_timeout(1800)
  assert (await counts(desktop))==c
  assert (await state(desktop))['time']==before['seconds']
  assert not (await candidate(desktop))['visible']
  results['mouse_paused_release_once']=before

  # Horizontal gestures and normal toolbar/cover interaction must not arm scrub selection.
  await reset(desktop)
  box=await desktop.locator('.speech-lyrics').bounding_box()
  x=box['x']+box['width']/2;y=box['y']+box['height']*.6
  await desktop.mouse.move(x,y);await desktop.mouse.down();await desktop.mouse.move(x+80,y+2);await desktop.mouse.up()
  await no_commit(desktop)
  cover=await desktop.locator('#albumCoverContainer').bounding_box()
  await desktop.mouse.move(cover['x']+20,cover['y']+20);await desktop.mouse.down();await desktop.mouse.move(cover['x']+20,cover['y']+90);await desktop.mouse.up()
  await no_commit(desktop)
  assert not (await candidate(desktop))['visible']
  results['horizontal_and_other_controls_no_seek']=True

  tablet=await browser.new_page(viewport={'width':1024,'height':768},device_scale_factor=2,is_mobile=True,has_touch=True)
  tablet.on('pageerror',lambda e: errors.append(str(e)))
  await load(tablet);await watch(tablet);await reset(tablet,delay=1250)
  await tablet.locator('#playPauseBtn').tap()
  g=await begin(tablet,True)
  before=await candidate(tablet)
  assert before['seconds']==(before['start']-1250)/1000,before
  await no_commit(tablet)
  assert not (await state(tablet))['paused']
  await tablet.screenshot(path=str(OUT/'drag-seek-tablet.png'))
  await end(tablet,g)
  st=await state(tablet);c=await counts(tablet)
  assert before['seconds']<=st['time']<before['seconds']+1 and not st['paused'],(before,st)
  assert c['commits']==[before['start']] and c['seeks']==1,c
  results['touch_playing_positive_delay']=before

  await reset(tablet,delay=-1000)
  g=await begin(tablet,True);before=await candidate(tablet)
  assert before['seconds']==before['start']/1000+1,before
  await end(tablet,g)
  assert (await state(tablet))['time']==before['seconds']
  results['touch_paused_negative_delay']=before

  await reset(tablet)
  await tablet.evaluate('player.state.isRangeMode=true;player.state.rangeStartTime=0;player.state.rangeEndTime=1')
  g=await begin(tablet,True);before=await candidate(tablet)
  assert before['seconds']>1
  await end(tablet,g)
  assert not (await state(tablet))['range']
  results['drag_exits_incompatible_range']=True

  for kind in ['cancel','multitouch','multitouch_outside','lost_capture','mode_change','outside','delay_change','resize']:
   await reset(tablet)
   g=await begin(tablet,True)
   assert (await candidate(tablet))['visible']
   if kind in ['multitouch','multitouch_outside']:
    await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':g['x'],'y':g['y'],'id':0},{'x':g['x']+35 if kind=='multitouch' else 10,'y':g['y']+35 if kind=='multitouch' else 100,'id':1}]})
   elif kind=='lost_capture':
    await tablet.evaluate('(()=>{const lp=player.getLyricPlayer();lp.getElement().releasePointerCapture(lp.pointer.id)})()')
    await tablet.wait_for_timeout(30)
   elif kind=='mode_change':
    await tablet.evaluate("document.getElementById('dragSeekMode').click()")
   elif kind=='outside':
    await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':g['box']['x']-30,'y':g['y'],'id':0}]})
    await tablet.wait_for_timeout(60)
    assert (await candidate(tablet))['label']==''
   elif kind=='delay_change':
    await tablet.evaluate('player.applyLyricDelay(500)')
   elif kind=='resize':
    await tablet.set_viewport_size({'width':1000,'height':768})
    await tablet.wait_for_timeout(100)
   await end(tablet,g,kind=='cancel')
   await no_commit(tablet)
   assert not (await candidate(tablet))['visible']
   results[f'{kind}_cancels_selection']=True
   if kind=='mode_change': await tablet.locator('#dragSeekMode').tap()
  await tablet.wait_for_timeout(5500)
  await no_commit(tablet)
  results['auto_follow_cannot_commit_cancelled_drag']=True

  await tablet.set_viewport_size({'width':1024,'height':768})
  await reset(tablet)
  b=await tablet.locator('.speech-lyrics').bounding_box();x=b['x']+b['width']/2;y=b['y']+b['height']*.65
  cdp=await tablet.context.new_cdp_session(tablet)
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0}]})
  await tablet.wait_for_timeout(550)
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y-100,'id':0}]})
  assert not (await candidate(tablet))['visible']
  assert not (await state(tablet))['following'] # Long holds can browse, never seek.
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]});await cdp.detach()
  await no_commit(tablet)
  results['long_press_then_move_does_not_seek']=True

  # The explicit switch restores browsing with no guide or commit, including its persisted setting.
  await tablet.locator('#dragSeekMode').tap()
  assert await tablet.locator('#dragSeekMode').get_attribute('aria-pressed')=='false'
  g=await begin(tablet,True);assert not (await candidate(tablet))['visible']
  await end(tablet,g);await no_commit(tablet)
  await load(tablet);assert await tablet.locator('#dragSeekMode').get_attribute('aria-pressed')=='false'
  await tablet.locator('#dragSeekMode').tap();await watch(tablet);await reset(tablet)
  results['browse_switch_and_persistence']=True

  # Clamp at each transcript end without seeking past the first or last sentence.
  await tablet.locator('#lyricFile').set_input_files({'name':'short.srt','mimeType':'text/plain','buffer':srt(3).encode()})
  await reset(tablet)
  g=await begin(tablet,True,dy=-400,start_fraction=.85);before=await candidate(tablet)
  assert before['start']==6000,before
  await end(tablet,g);assert (await state(tablet))['time']==6
  await reset(tablet,time=6)
  g=await begin(tablet,True,dy=400,start_fraction=.2);before=await candidate(tablet)
  assert before['start']==0,before
  await end(tablet,g);assert (await state(tablet))['time']==0
  results['first_last_line_bounds']=True

  # Inject malformed/untimed metadata at the renderer boundary; never guess a seek timestamp.
  for value in ['NaN','120000']:
   await reset(tablet)
   await tablet.evaluate(f'player.getLyricPlayer().currentLyricLineObjects.forEach(l=>l.getLine().startTime={value})')
   g=await begin(tablet,True,dy=-70)
   preview=await candidate(tablet)
   assert preview['visible'] and preview['seconds'] is None,preview
   await end(tablet,g);await no_commit(tablet)
  results['missing_or_out_of_media_timestamps_no_seek']=True
  await tablet.evaluate('player.getAudio().removeAttribute("src");player.getAudio().load()')
  await tablet.wait_for_timeout(100);await tablet.evaluate('window.commits=[];window.seeks=0')
  g=await begin(tablet,True,dy=-70)
  assert (await candidate(tablet))['label']==''
  await end(tablet,g);await no_commit(tablet)
  results['no_audio_no_seek']=True

  assert not errors,errors
  results['page_errors']=errors
  (OUT/'drag-seek-results.json').write_text(json.dumps(results,indent=2))
  print(json.dumps(results,indent=2))
  await browser.close()

if __name__=='__main__':asyncio.run(main())
