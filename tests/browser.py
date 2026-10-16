"""Synthetic media only. Chromium desktop + iPad-size touch emulation, NOT physical iPad."""
import asyncio, json, math, os, struct, wave
from pathlib import Path
from playwright.async_api import async_playwright

OUT=Path('test-results'); OUT.mkdir(exist_ok=True)
BASE=os.environ.get('PLAYER_URL','http://localhost:5173/')
with wave.open(str(OUT/'synthetic.wav'),'wb') as f:
 f.setparams((1,2,8000,0,'NONE','not compressed'))
 f.writeframes(b''.join(struct.pack('<h',int(1800*math.sin(2*math.pi*440*i/8000))) for i in range(8000*60)))
def stamp(seconds):
 return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02},000'
def srt(n):
 return '\n\n'.join(f'{i+1}\n{stamp(i*3)} --> {stamp((i+1)*3)}\nSynthetic sentence {i+1}. Practice clearly.' for i in range(n))

async def load(page,n=20):
 await page.goto(BASE)
 await page.wait_for_function('window.player !== undefined')
 await page.evaluate('window.player.state.autoPlay=false')
 await page.locator('#musicFile').set_input_files(str(OUT/'synthetic.wav'))
 await page.wait_for_function('document.querySelector("audio").duration === 60')
 await page.locator('#lyricFile').set_input_files({'name':'synthetic.srt','mimeType':'text/plain','buffer':srt(n).encode()})
 await page.wait_for_function(f'window.player.getLyricPlayer().getLyricLines().length === {n}')
 await page.wait_for_timeout(600)
 await page.evaluate("player.getBackground().setStaticMode(true)")

async def tapline(page,index,touch=False):
 # Playwright waits for the animated target to settle and checks actual hit testing.
 line=page.locator(f'.speech-lyrics [aria-label^="Seek to Synthetic sentence {index+1}."]')
 if touch:
  await line.tap()
  box=await line.bounding_box()
  await page.touchscreen.tap(box['x']+box['width']/2,box['y']+box['height']/2)
 else: await line.dblclick(delay=80)
 await page.wait_for_timeout(150)

async def state(page):
 return await page.evaluate('''()=>({time:player.getAudio().currentTime,lyric:player.getLyricPlayer().getCurrentTime(),paused:player.getAudio().paused,following:player.getLyricPlayer().isFollowing,range:player.state.isRangeMode,hot:[...player.getLyricPlayer().hotLines],visualActive:player.getLyricPlayer().currentLyricLineObjects.flatMap((l,i)=>l.getElement().className.includes('_active_')?[i]:[])})''')

async def drag(page,dx=0,dy=-180):
 box=await page.locator('.speech-lyrics').bounding_box()
 x=box['x']+box['width']/2;y=box['y']+box['height']*.6
 cdp=await page.context.new_cdp_session(page)
 await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
 for i in range(1,13):
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x+dx*i/12,'y':y+dy*i/12}]})
  await page.wait_for_timeout(20)
 gesture=await page.evaluate('''()=>{const lp=player.getLyricPlayer();return {manual:lp.manual,mode:lp.isDragSeekEnabled,pointer:lp.pointer&&{dragging:lp.pointer.dragging,eligible:lp.pointer.eligible,inside:lp.pointer.inside}}}''')
 assert gesture['pointer'] and gesture['pointer']['dragging'],gesture
 await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
 await cdp.detach()

async def main():
 results={};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True,args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  desktop=await browser.new_page(viewport={'width':1280,'height':900})
  desktop.on('pageerror',lambda e: errors.append(str(e)))
  await load(desktop)
  await desktop.locator('.speech-lyrics [aria-label^="Seek to Synthetic sentence 2."]').click()
  assert (await state(desktop))['time']==0
  await desktop.wait_for_timeout(400)
  assert not (await state(desktop))['paused']
  await desktop.locator('#playPauseBtn').click()
  await tapline(desktop,1)
  st=await state(desktop);assert abs(st['time']-3)<.05 and st['paused'] and 1 in st['hot'] and 1 in st['visualActive'],st
  results['desktop_paused_double_click']=st
  await desktop.locator('#playPauseBtn').click()
  await desktop.wait_for_timeout(300)
  await tapline(desktop,2)
  st=await state(desktop);assert 6<=st['time']<6.8 and not st['paused'] and 2 in st['hot'] and 2 in st['visualActive'],st
  results['desktop_playing_double_click']=st
  await desktop.evaluate('player.getAudio().pause();player.applyLyricDelay(1500);player.seekAudio(0)')
  await desktop.wait_for_timeout(500);await tapline(desktop,1)
  st=await state(desktop);assert abs(st['time']-1.5)<.05 and st['lyric']==3000,st
  results['positive_delay']=st
  await desktop.evaluate('player.applyLyricDelay(-1000);player.seekAudio(0)')
  await desktop.wait_for_timeout(500);await tapline(desktop,1)
  st=await state(desktop);assert abs(st['time']-4)<.05 and st['lyric']==3000,st
  results['negative_delay']=st
  await desktop.evaluate('player.applyLyricDelay(0);player.state.isRangeMode=true;player.state.rangeStartTime=0;player.state.rangeEndTime=5;player.seekAudio(0)')
  await desktop.wait_for_timeout(500);await tapline(desktop,2)
  st=await state(desktop);assert abs(st['time']-6)<.05 and not st['range'],st
  results['sentence_leaves_range']=st
  await desktop.evaluate('player.state.isRangeMode=true;player.state.rangeStartTime=10;player.state.rangeEndTime=20;player.seekAudio(30)')
  st=await state(desktop);assert abs(st['time']-19.999)<.05 and st['range'],st
  results['other_seeks_clamp_range']=st
  await desktop.evaluate('player.exitRangeMode();player.seekAudio(0)')
  await desktop.wait_for_timeout(500)
  await desktop.evaluate('player.getLyricPlayer().currentLyricLineObjects[1].getElement().focus()')
  await desktop.keyboard.press('Enter')
  st=await state(desktop);assert st['time']==3,st
  results['keyboard_sentence']=st
  await desktop.keyboard.press('ArrowRight');await desktop.keyboard.press('ArrowLeft')
  await desktop.wait_for_timeout(100)
  st=await state(desktop);assert st['time']==3 and st['lyric']==3000,st
  results['rapid_seek_no_timer_race']=st
  await desktop.wait_for_timeout(800)
  await desktop.screenshot(path=str(OUT/'desktop.png'))

  tablet=await browser.new_page(viewport={'width':1024,'height':768},device_scale_factor=2,is_mobile=True,has_touch=True)
  tablet.on('pageerror',lambda e: errors.append(str(e)))
  await load(tablet)
  await tablet.evaluate('window.activations=0;player.getLyricPlayer().addEventListener("line-activate",()=>window.activations++)')
  await tablet.locator('.speech-lyrics [aria-label^="Seek to Synthetic sentence 2."]').tap()
  assert (await state(tablet))['time']==0
  await tablet.wait_for_timeout(400)
  assert not (await state(tablet))['paused']
  await tablet.locator('#playPauseBtn').tap()
  await tapline(tablet,1,True)
  st=await state(tablet);assert st['time']==3 and st['paused'],st
  assert await tablet.evaluate('window.activations')==1
  results['touch_paused_double_tap_once']=st
  await tablet.locator('#playPauseBtn').tap();await tablet.wait_for_timeout(200)
  await tapline(tablet,2,True)
  st=await state(tablet);assert 6<=st['time']<6.8 and not st['paused'],st
  results['touch_playing_double_tap']=st
  await tablet.locator('#dragSeekMode').tap() # Explicit browsing mode retains inertial scrolling.
  assert await tablet.locator('#dragSeekMode').get_attribute('aria-pressed')=='false'
  await tablet.evaluate('player.getAudio().pause();player.seekAudio(6)')
  await tablet.wait_for_timeout(500);await drag(tablet)
  st=await state(tablet);assert st['time']==6 and not st['following'],st
  assert await tablet.evaluate('window.activations')==2
  results['drag_does_not_seek']=st
  await tablet.wait_for_timeout(1100)
  # Once inertia has settled, advancing across a sentence must not move the manual anchor.
  before=await tablet.evaluate('player.getLyricPlayer().currentLyricLineObjects[5].getElement().getBoundingClientRect().y')
  await tablet.evaluate('player.getAudio().currentTime=12')
  await tablet.wait_for_timeout(250)
  after=await tablet.evaluate('player.getLyricPlayer().currentLyricLineObjects[5].getElement().getBoundingClientRect().y')
  assert abs(after-before)<3,(before,after)
  results['manual_anchor_delta_px']=after-before
  await tablet.locator('#followPlayback').tap()
  assert (await state(tablet))['following']
  await drag(tablet,dy=-70)
  await tablet.wait_for_timeout(6500)
  assert (await state(tablet))['following']
  results['explicit_and_idle_follow']=True
  # Native Chromium touch cancellation, long press, and multi-touch must not seek.
  await tablet.evaluate('player.seekAudio(0)')
  await tablet.wait_for_timeout(500)
  target=tablet.locator('.speech-lyrics [aria-label^="Seek to Synthetic sentence 2."]')
  await target.wait_for(state='visible')
  box=await target.bounding_box(); x=box['x']+box['width']/2; y=box['y']+box['height']/2
  cdp=await tablet.context.new_cdp_session(tablet)
  count=await tablet.evaluate('window.activations')
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0}]})
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchCancel','touchPoints':[]})
  await tablet.wait_for_timeout(400)
  assert (await state(tablet))['paused']
  assert await tablet.evaluate('window.activations')==count
  await tablet.wait_for_timeout(400)
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0}]})
  await tablet.wait_for_timeout(550)
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  await tablet.wait_for_timeout(400)
  assert (await state(tablet))['paused']
  assert await tablet.evaluate('window.activations')==count
  await tablet.wait_for_timeout(400)
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0}]})
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0},{'x':x+40,'y':y+40,'id':1}]})
  await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
  await tablet.wait_for_timeout(400)
  assert (await state(tablet))['paused']
  assert await tablet.evaluate('window.activations')==count
  assert (await state(tablet))['time']==0
  results['cancel_long_press_multitouch_no_seek']=True
  assert await tablet.evaluate('visualViewport.scale')==1
  results['no_chromium_double_tap_zoom']=True
  await cdp.detach()
  dims=await tablet.evaluate('''()=>{const c=player.getBackground().getElement();return {w:c.width,h:c.height,cssW:c.clientWidth,cssH:c.clientHeight,dpr:devicePixelRatio}}''')
  assert dims['w']==dims['cssW']*2 and dims['h']==dims['cssH']*2,dims
  results['background_dpr2']=dims
  await tablet.set_viewport_size({'width':768,'height':1024});await tablet.wait_for_timeout(300)
  dims=await tablet.evaluate('''()=>{const c=player.getBackground().getElement();return {w:c.width,h:c.height,cssW:c.clientWidth,cssH:c.clientHeight}}''')
  assert dims['w']==dims['cssW']*2 and dims['h']==dims['cssH']*2,dims
  results['rotation_background']=dims
  await tablet.screenshot(path=str(OUT/'tablet-portrait.png'))
  # Restoring saved background scale and resetting must not apply DPR twice.
  await tablet.evaluate("player.state.backgroundRenderScale=.5;player.saveBackgroundSettings();player.state.backgroundRenderScale=1;player.loadBackgroundSettings()")
  await tablet.wait_for_timeout(200)
  restored=await tablet.evaluate("(()=>{const c=player.getBackground().getElement();return {w:c.width,cssW:c.clientWidth}})()")
  assert restored['w']==restored['cssW'],restored
  results['saved_half_scale_restore']=True
  await tablet.evaluate("player.resetPlayer()")
  await tablet.wait_for_timeout(200)
  reset=await tablet.evaluate("(()=>{const c=player.getBackground().getElement();return {w:c.width,cssW:c.clientWidth}})()")
  assert reset['w']==reset['cssW']*2,reset
  results['reset_scale']=True
  # Full Reset now restores all preferences, including the default seek mode.
  # The following cases specifically exercise manual browsing and A–B wrapping.
  assert await tablet.locator('#dragSeekMode').get_attribute('aria-pressed')=='true'
  await tablet.locator('#dragSeekMode').tap()
  await tablet.locator('#musicFile').set_input_files(str(OUT/'synthetic.wav'))
  await tablet.wait_for_function('player.getAudio().duration===60')
  await tablet.evaluate('player.getAudio().pause();player.state.isRangeMode=true;player.state.rangeStartTime=0;player.state.rangeEndTime=1;player.seekAudio(.8)')
  await tablet.locator('#lyricFile').set_input_files({'name':'synthetic.srt','mimeType':'text/plain','buffer':srt(20).encode()})
  await tablet.wait_for_timeout(500)
  await drag(tablet,dy=-70)
  await tablet.evaluate('player.getAudio().play()')
  await tablet.wait_for_timeout(600)
  st=await state(tablet)
  assert st['time']<1 and not st['following'],st
  results['range_wrap_preserves_manual']=True
  await tablet.evaluate('player.getAudio().pause();player.exitRangeMode()')
  # Long list uses synthetic parser input. Report measurement; no physical-device FPS claim.
  await tablet.set_viewport_size({'width':1024,'height':768})
  await tablet.evaluate('player.getBackground().setStaticMode(true)')
  import time
  loaded_at=time.monotonic()
  await tablet.locator('#lyricFile').set_input_files({'name':'long-synthetic.srt','mimeType':'text/plain','buffer':srt(2000).encode()})
  await tablet.wait_for_function('player.getLyricPlayer().getLyricLines().length===2000',timeout=60000)
  load_seconds=time.monotonic()-loaded_at
  await tablet.wait_for_timeout(1500)
  perf=await tablet.evaluate('''async()=>{let times=[];let lp=player.getLyricPlayer();for(let i=0;i<120;i++){await new Promise(requestAnimationFrame);let t=performance.now();lp.update(16.667);times.push(performance.now()-t)}times.sort((a,b)=>a-b);return {lines:lp.getLyricLines().length,mounted:lp.getElement().querySelectorAll('[role=button]').length,animated:lp.animated.size,updateMedianMs:times[60],updateP95Ms:times[114]}}''')
  assert perf['mounted']<50 and perf['animated']<50,perf
  perf['loadSeconds']=round(load_seconds,3)
  results['long_list']=perf
  await drag(tablet,dy=-220)
  assert not (await state(tablet))['following']
  await tablet.screenshot(path=str(OUT/'tablet-long-list.png'))
  # Published static assets and same-build source download must be available.
  from urllib.parse import urljoin
  for path in ['manifest.webmanifest','icons/icon-192x192.png','jsmediatags.min.js','source/amll-speech-player.tar.gz']:
   response=await tablet.request.get(urljoin(BASE,path))
   assert response.status==200,(path,response.status)
  results['static_assets_and_source_download']=True
  results['page_errors']=errors
  assert not errors,errors
  (OUT/'browser-results.json').write_text(json.dumps(results,indent=2))
  print(json.dumps(results,indent=2))
  await browser.close()
if __name__ == '__main__':
 asyncio.run(main())
