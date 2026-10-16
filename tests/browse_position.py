"""Browsing stays put; explicit Follow and seeks restore automatic alignment.
Synthetic media in Chromium; touch/viewport emulation is not physical Safari.
"""
import asyncio,json
from playwright.async_api import async_playwright
from browser import load,state,OUT
from drag_seek import begin,end,candidate,watch,counts,reset

LRC='\n'.join(f'[{i*3//60:02}:{i*3%60:02}.00]Sentence {i:02}. '+('A longer sentence for practising pronunciation that wraps across several lines on a phone.' if i%2 else 'Read clearly.') for i in range(20))

async def mode(page,enabled):
 if await page.locator('#dragSeekMode').get_attribute('aria-pressed')!=str(enabled).lower():
  await page.locator('#dragSeekMode').click()

async def snapshot(page,index=None):
 return await page.evaluate('''index=>{const p=player.getLyricPlayer();if(index===null){index=p.currentLyricLineObjects.findIndex(l=>{const top=p.targetTop.get(l),h=p.lyricLinesSize.get(l)?.[1];return l.getElement().isConnected&&top>=0&&top+h<=p.size[1]});}const l=p.currentLyricLineObjects[index],r=l.getElement().getBoundingClientRect();return {index,center:r.y+r.height/2,offset:p.scrollOffset,anchor:p.manualAnchor,following:p.isFollowing,targets:p.currentLyricLineObjects.map(l=>p.targetTop.get(l))}}''',index)

def stays(before,after):
 assert not after['following'],after
 assert abs(after['offset']-before['offset'])<.1 and after['anchor']==before['anchor'],(before,after)
 assert abs(after['center']-before['center'])<2,(before,after)
 assert max(abs(a-b) for a,b in zip(after['targets'],before['targets']))<.1,(before,after)

async def aligned(page):
 await page.wait_for_function('''()=>{const p=player.getLyricPlayer(),l=p.currentLyricLineObjects[p.scrollToIndex];return p.isFollowing&&Math.abs(l.lineTransforms.posY.getCurrentPosition()+p.lyricLinesSize.get(l)[1]/2-p.size[1]*p.alignPosition)<3}''',timeout=5000)
 a=await page.evaluate('''()=>{const p=player.getLyricPlayer(),l=p.currentLyricLineObjects[p.scrollToIndex],h=p.lyricLinesSize.get(l)[1];return {following:p.isFollowing,offset:p.scrollOffset,target:p.targetTop.get(l)+h/2,expected:p.size[1]*p.alignPosition,actual:l.lineTransforms.posY.getCurrentPosition()+h/2}}''')
 assert a['following'] and a['offset']==0 and abs(a['target']-a['expected'])<1 and abs(a['actual']-a['expected'])<3,a
 assert not await page.locator('#followPlayback').is_visible()

async def browse(page,kind,touch):
 if kind=='wheel':
  b=await page.locator('.speech-lyrics').bounding_box()
  await page.mouse.move(b['x']+b['width']/2,b['y']+b['height']/2)
  await page.mouse.wheel(0,85)
 else:
  await mode(page,False)
  g=await begin(page,touch,dy=-60,start_fraction=.6)
  # Release a moving gesture, exercising the existing inertial browse path.
  if g['cdp']:await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':g['x'],'y':g['y']-18,'id':0}]})
  else:await page.mouse.move(g['x'],g['y']-18)
  await end(page,g)
 await page.wait_for_timeout(1300)
 assert not (await state(page))['following']

async def place(page,index,fraction):
 p=await page.evaluate('''({index,fraction})=>{const p=player.getLyricPlayer(),l=p.currentLyricLineObjects[index],r=p.getElement().getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2,delta:p.targetTop.get(l)+p.lyricLinesSize.get(l)[1]/2-p.size[1]*fraction}}''',{'index':index,'fraction':fraction})
 await page.mouse.move(p['x'],p['y']);await page.mouse.wheel(0,p['delta']);await page.wait_for_timeout(250)

async def double(page,index,touch):
 p=await page.evaluate('''i=>{const r=player.getLyricPlayer().currentLyricLineObjects[i].getElement().getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}}''',index)
 if touch:
  await page.touchscreen.tap(**p);await page.wait_for_timeout(60);await page.touchscreen.tap(**p)
 else:await page.mouse.dblclick(**p,delay=60)
 await page.wait_for_timeout(200)

async def main():
 results={'cases':{},'page_errors':[],'limits':'Local production build, synthetic media, Chromium mouse/touch emulation; no physical iPad Safari.'}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  for name,w,h,touch in [('desktop',1280,900,False),('tablet',1024,768,True),('phone',390,844,True)]:
   page=await browser.new_page(viewport={'width':w,'height':h},has_touch=touch,is_mobile=touch)
   page.on('pageerror',lambda e:results['page_errors'].append(str(e)))
   await load(page)
   await page.locator('#lyricFile').set_input_files({'name':'browse.lrc','mimeType':'text/plain','buffer':LRC.encode()})
   await page.wait_for_timeout(700);await watch(page)
   for playing in [False,True]:
    for kind in ['wheel','drag']:
     await reset(page,time=19)
     if playing:await page.evaluate('player.getAudio().play()')
     await browse(page,kind,touch)
     before=await snapshot(page)
     await page.wait_for_timeout(6200)
     stays(before,await snapshot(page,before['index']))
     s=await state(page)
     assert s['paused']==(not playing) and await counts(page)=={'commits':[],'seeks':0},s
     if playing:assert s['time']>25
     assert await page.locator('#followPlayback').is_visible()
     await page.screenshot(path=str(OUT/f'browse-{name}-{kind}.png'))
     await page.locator('#followPlayback').click();await aligned(page)
     assert (await state(page))['paused']==(not playing)
     # Keyboard seek is explicit navigation and must also leave browse mode.
     await browse(page,'wheel',touch)
     prior=(await state(page))['time']
     await page.keyboard.press('ArrowLeft');await aligned(page)
     s=await state(page)
     assert s['paused']==(not playing) and abs(s['time']-(prior-10))<(2 if playing else .01),s
     results['cases'][f'{name}_{kind}_playing_{playing}']={'idle_wait_ms':6200,'no_seek_during_browse':True,'follow_button_and_keyboard_seek_realign':True}
     print(f'PASS {name} {kind} playing={playing}',flush=True)
    for label,fraction,index in [('top',.2,7),('middle',.5,6),('bottom',.8,7)]:
     await reset(page,time=12 if label=='top' else 30)
     if playing:await page.evaluate('player.getAudio().play()')
     await place(page,index,fraction)
     await double(page,index,touch)
     s=await state(page)
     assert s['following'] and s['paused']==(not playing) and index*3<=s['time']<index*3+.8,s
     assert await counts(page)=={'commits':[index*3000],'seeks':1}
     await aligned(page)
     results['cases'][f'{name}_double_{label}_playing_{playing}']=True
    await mode(page,True)
    for dy in [-80,80]:
     await reset(page,time=19)
     if playing:await page.evaluate('player.getAudio().play()')
     g=await begin(page,touch,dy=dy,start_fraction=.5);c=await candidate(page)
     assert c['start'] is not None,c
     await end(page,g);s=await state(page)
     assert s['following'] and s['paused']==(not playing) and c['seconds']<=s['time']<c['seconds']+.8,s
     assert await counts(page)=={'commits':[c['start']],'seeks':1}
     await aligned(page)
     results['cases'][f'{name}_drag_seek_{dy}_playing_{playing}']=True
   # Cancelled drag-to-seek is still browsing, never an implicit seek/follow.
   await reset(page,time=19)
   g=await begin(page,touch,dy=-70)
   if touch:await end(page,g,cancel=True)
   else:
    await page.evaluate('player.getLyricPlayer().cancelPointer()');await end(page,g)
   before=await snapshot(page);await page.wait_for_timeout(6200)
   stays(before,await snapshot(page,before['index']))
   assert await counts(page)=={'commits':[],'seeks':0}
   await page.locator('#followPlayback').click();await aligned(page)
   results['cases'][f'{name}_cancelled_selection_stays_browsing']=True
   await page.close()
  await browser.close()
 assert not results['page_errors'],results
 (OUT/'browse-position-results.json').write_text(json.dumps(results,indent=2)+'\n')
 print(json.dumps(results,indent=2))

if __name__=='__main__':asyncio.run(main())
