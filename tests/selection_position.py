"""Selected sentences retain their viewport until explicit Follow.

Real Chromium mouse/touch input and wall-clock idle waits, synthetic local media.
This does not constitute physical iPad/Safari coverage.
"""
import asyncio,json
from playwright.async_api import async_playwright
from browser import load,state,OUT
from drag_seek import begin,end,candidate,watch,counts,reset

TEXTS=[f'Sentence {i:02}. '+('A deliberately longer sentence for practising pronunciation, which wraps across multiple lines on a narrow screen.' if i%2 else 'Read clearly.') for i in range(20)]
LRC='\n'.join(f'[{i*3//60:02}:{i*3%60:02}.00]{text}' for i,text in enumerate(TEXTS))

async def geometry(page,index):
 return await page.evaluate('''i=>{const lp=player.getLyricPlayer(),l=lp.currentLyricLineObjects[i],e=l.getElement(),r=e.getBoundingClientRect();return {
  center:r.y+r.height/2,top:lp.targetTop.get(l),height:lp.lyricLinesSize.get(l)[1],
  offset:lp.scrollOffset,anchor:lp.manualAnchor,following:lp.isFollowing,held:lp.isPositionHeld,
  timer:lp.followTimer,connected:e.isConnected,targets:lp.currentLyricLineObjects.map(l=>lp.targetTop.get(l))};}''',index)

def stationary(before,after):
 assert after['connected'] and after['held'] and not after['following'],after
 assert abs(after['center']-before['center'])<2,(before,after)
 assert abs(after['offset']-before['offset'])<.1,(before,after)
 assert max(abs(a-b) for a,b in zip(before['targets'],after['targets']))<.1,(before,after)

async def double(page,index,touch):
 point=await page.evaluate('''i=>{const e=player.getLyricPlayer().currentLyricLineObjects[i].getElement(),r=e.getBoundingClientRect();return {x:r.x+r.width/2,y:r.y+r.height/2}}''',index)
 if touch:
  await page.touchscreen.tap(**point);await page.wait_for_timeout(60);await page.touchscreen.tap(**point)
 else:await page.mouse.dblclick(**point,delay=60)

async def follow(page):
 await page.locator('#followPlayback').click()
 assert (await state(page))['following']
 assert not await page.evaluate('player.getLyricPlayer().isPositionHeld')
 await page.wait_for_timeout(700)

async def position(page,index,fraction):
 # Wheel browsing puts the selected sentence at a measured viewport position,
 # and arms the real pre-existing idle timer before the double tap.
 info=await page.evaluate('''({index,fraction})=>{const p=player.getLyricPlayer(),r=p.getElement().getBoundingClientRect(),l=p.currentLyricLineObjects[index],h=p.lyricLinesSize.get(l)[1],inset=parseFloat(getComputedStyle(p.getElement()).paddingTop)||0;return {x:r.x+r.width/2,y:r.y+r.height/2,delta:p.targetTop.get(l)+h/2-p.size[1]*fraction,desired:r.y+inset+p.size[1]*fraction}}''',{'index':index,'fraction':fraction})
 await page.mouse.move(info['x'],info['y']);await page.mouse.wheel(0,info['delta']);await page.wait_for_timeout(350)
 before=await geometry(page,index)
 assert abs(before['center']-info['desired'])<2 and before['timer'] and not before['held'],(info,before)
 return before

async def main():
 results={'cases':{},'page_errors':[],'limits':'Local production build, synthetic WAV/LRC, Chromium mouse/touch emulation; no physical iPad Safari.'}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  for name,w,h,touch in [('desktop',1280,900,False),('tablet',1024,768,True),('phone',390,844,True)]:
   page=await browser.new_page(viewport={'width':w,'height':h},has_touch=touch,is_mobile=touch)
   page.on('pageerror',lambda e:results['page_errors'].append(str(e)))
   await load(page)
   await page.locator('#lyricFile').set_input_files({'name':'position.lrc','mimeType':'text/plain','buffer':LRC.encode()})
   await page.wait_for_timeout(700);await watch(page)
   for playing in [False,True]:
    for label,fraction,index,direction in [('top',.2,7,1),('middle',.5,6,-1),('bottom',.8,7,-1)]:
     await reset(page,time=index*3-direction*6)
     if playing:await page.evaluate('player.getAudio().play()')
     before=await position(page,index,fraction)
     await double(page,index,touch);await page.wait_for_timeout(250)
     s=await state(page)
     assert s['paused']==(not playing) and index*3<=s['time']<index*3+.8,s
     assert await counts(page)=={'commits':[index*3000],'seeks':1}
     stationary(before,await geometry(page,index))
     # Cross the old five-second timer and multiple lyric boundaries in playback.
     await page.wait_for_timeout(5300)
     stationary(before,await geometry(page,index))
     assert await page.locator('#followPlayback').is_visible()
     assert (await state(page))['paused']==(not playing)
     assert await counts(page)=={'commits':[index*3000],'seeks':1}
     if playing:assert (await state(page))['time']>index*3+5
     # Same-row double-tap replay uses exactly one seek and keeps the same viewport.
     await page.evaluate('window.commits=[];window.seeks=0')
     await double(page,index,touch);await page.wait_for_timeout(250)
     assert await counts(page)=={'commits':[index*3000],'seeks':1}
     stationary(before,await geometry(page,index))
     # Other explicit navigation may change audio, but cannot silently enable Follow.
     await page.evaluate('player.seekAudio(player.getAudio().currentTime+3)')
     await page.wait_for_timeout(250);stationary(before,await geometry(page,index))
     await follow(page)
     # Follow really aligns the playing row again, rather than only hiding the button.
     align=await page.evaluate('''()=>{const p=player.getLyricPlayer(),l=p.currentLyricLineObjects[p.scrollToIndex];return {center:p.targetTop.get(l)+p.lyricLinesSize.get(l)[1]/2,expected:p.size[1]*p.alignPosition}}''')
     assert abs(align['center']-align['expected'])<1,align
     results['cases'][f'{name}_double_{label}_playing_{playing}']={'direction':direction,'wrapped_height':before['height'],'idle_wait_ms':5300,'same_row_replay':True,'explicit_follow':True}
     print(f'PASS {name} double {label} playing={playing}',flush=True)
    for dy in [-85,85]:
     await reset(page,time=19)
     if playing:await page.evaluate('player.getAudio().play()')
     g=await begin(page,touch,dy=dy,start_fraction=.5)
     c=await candidate(page);assert c['start'] is not None,c
     index=int(c['start']/3000);before=await geometry(page,index)
     await end(page,g)
     assert await counts(page)=={'commits':[c['start']],'seeks':1}
     stationary(before,await geometry(page,index))
     assert (await state(page))['paused']==(not playing)
     await page.wait_for_timeout(5300);stationary(before,await geometry(page,index))
     # Browsing/cancellation while held must not re-arm the idle follow timer.
     await page.evaluate('player.getLyricPlayer().setDragSeekEnabled(false)')
     g=await begin(page,touch,dy=25,start_fraction=.5)
     await end(page,g,cancel=touch)
     await page.wait_for_timeout(650)
     held=await geometry(page,index)
     await page.wait_for_timeout(5300);stationary(held,await geometry(page,index))
     await follow(page)
     await page.evaluate('player.getLyricPlayer().setDragSeekEnabled(true)')
     results['cases'][f'{name}_drag_{dy}_playing_{playing}']={'released_start':c['start'],'idle_wait_ms':5300,'browse_after_selection_stays_held':True}
     print(f'PASS {name} drag {dy} playing={playing}',flush=True)
   # A double tap while ordinary playback is moving its native springs freezes
   # the selected row's displayed position, not a newer queued anchor target.
   await reset(page,time=18);await page.evaluate('player.getAudio().play()')
   await page.evaluate('''()=>{const p=player.getLyricPlayer(),hold=p.holdPosition.bind(p);p.holdPosition=time=>{
    const l=p.currentLyricLineObjects.find(l=>l.getLine().startTime===time),r=l.getElement().getBoundingClientRect();
    window.heldBefore={center:r.y+r.height/2,following:p.isFollowing};hold(time);
   };player.getAudio().currentTime=21}''')
   await page.wait_for_timeout(60)
   index=await page.evaluate('''()=>{const p=player.getLyricPlayer(),r=p.getElement().getBoundingClientRect();return p.currentLyricLineObjects.findIndex(l=>{const e=l.getElement(),b=e.getBoundingClientRect();return e.isConnected&&b.y>r.y+60&&b.bottom<r.bottom-50})}''')
   assert index>=0
   await double(page,index,touch);await page.wait_for_timeout(350)
   before=await page.evaluate('window.heldBefore');after=await geometry(page,index)
   assert before['following'] and after['held'] and abs(before['center']-after['center'])<2,(before,after)
   await page.wait_for_timeout(5300)
   assert abs(before['center']-(await geometry(page,index))['center'])<2
   await follow(page)
   results['cases'][f'{name}_selection_during_follow_animation']=True
   # Browsing without selection still automatically follows after idle.
   await reset(page,time=18);await page.evaluate('player.getLyricPlayer().setDragSeekEnabled(false)')
   g=await begin(page,touch,dy=-50,start_fraction=.5);await end(page,g)
   assert not (await state(page))['following']
   await page.wait_for_timeout(6300)
   assert (await state(page))['following'] and await counts(page)=={'commits':[],'seeks':0}
   results['cases'][f'{name}_unselected_browse_idle_follow']=True
   await position(page,7,.2);await double(page,7,touch);await page.wait_for_timeout(300)
   await page.screenshot(path=str(OUT/f'selection-position-{name}.png'))
   button=await page.locator('#followPlayback').bounding_box()
   assert button and button['x']>=0 and button['y']>=0 and button['x']+button['width']<=w and button['y']+button['height']<=h,button
   # AMLL inserts an interlude spacer before captions that start after silence.
   # Removing that spacer on a line seek must not pull the selected row upward.
   await page.evaluate('player.getAudio().pause();player.getLyricPlayer().resetScroll();player.seekAudio(0)')
   gaps='1\n00:00:10,000 --> 00:00:12,000\nOpening sentence.\n\n2\n00:00:20,000 --> 00:00:22,000\nNext sentence.\n\n3\n00:00:30,000 --> 00:00:32,000\nLast sentence.'
   await page.locator('#lyricFile').set_input_files({'name':'silence.srt','mimeType':'text/plain','buffer':gaps.encode()})
   await page.wait_for_timeout(800)
   assert await page.evaluate('!!player.getLyricPlayer().getCurrentInterlude()')
   before=await geometry(page,0);assert before['following']
   await page.evaluate('window.commits=[];window.seeks=0')
   await double(page,0,touch);await page.wait_for_timeout(350)
   after=await geometry(page,0)
   assert after['held'] and abs(after['center']-before['center'])<2,(before,after)
   assert await counts(page)=={'commits':[10000],'seeks':1}
   assert (await state(page))['time']==10 and (await state(page))['paused']
   await page.wait_for_timeout(5300);stationary(after,await geometry(page,0))
   await follow(page)
   results['cases'][f'{name}_opening_interlude_does_not_shift_selection']=True
   await page.close()
  await browser.close()
 assert not results['page_errors'],results
 (OUT/'selection-position-results.json').write_text(json.dumps(results,indent=2))
 print(json.dumps(results,indent=2))

if __name__=='__main__':asyncio.run(main())
