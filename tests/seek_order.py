"""Seek ordering regression: synthetic MP3/LRC, actual geometry and model checks.

Chromium only, including tablet-size touch input; this is not Safari coverage.
Run with PLAYER_URL for either local preview or the existing production site.
"""
import asyncio, json, os, subprocess
from playwright.async_api import async_playwright
from browser import BASE, OUT, state
from drag_seek import begin, end, candidate, watch, counts

ORDERED = '\n'.join(f'[{i*3//60:02}:{i*3%60:02}.00]Synthetic line {i:02}. Read this deliberately long sentence clearly and slowly.' for i in range(20))
UNORDERED = '''[00:09.00]Nine
[00:03.00]Three A
[00:03.00]Three B
[00:00.00]Zero
[00:06.00][00:12.00]Repeat
[00:15.00]Last'''
EXPECTED = [(0,3000,'Zero'),(3000,6000,'Three A'),(3000,6000,'Three B'),(6000,9000,'Repeat'),(9000,12000,'Nine'),(12000,15000,'Repeat'),(15000,20000,'Last')]
SNAP = '''()=>{const lp=player.getLyricPlayer();return {
 time:lp.currentTime, anchor:lp.scrollToIndex, hot:[...lp.hotLines].sort((a,b)=>a-b),
 lines:lp.currentLyricLineObjects.map((l,i)=>{const e=l.getElement(),r=e.getBoundingClientRect();return {
 i,start:l.getLine().startTime,end:l.getLine().endTime,text:l.getLine().words.map(w=>w.word).join(''),
 target:lp.targetTop.get(l), pos:l.lineTransforms.posY.getCurrentPosition(),
 queue:l.lineTransforms.posY.queuePosition??null, mounted:e.isConnected,
 y:r.y,height:r.height,active:e.className.includes('_active_'),animated:lp.animated.has(l)}})}}'''

async def upload(page, content):
 await page.locator('#lyricFile').set_input_files({'name':'synthetic.lrc','mimeType':'text/plain','buffer':content.encode()})
 await page.wait_for_timeout(800)

async def frames(page, n=3):
 await page.evaluate('(n)=>new Promise(resolve=>{function step(){if(--n<=0)resolve();else requestAnimationFrame(step)}requestAnimationFrame(step)})',n)

def geometry(s):
 mounted=[l for l in s['lines'] if l['mounted']]
 assert mounted, s
 assert all(abs(l['pos']-l['target'])<.3 for l in mounted), ('stale transform',mounted)
 assert all(b['y']>a['y'] for a,b in zip(mounted,mounted[1:])), ('visual order',mounted)
 assert all(l['queue'] is None or abs(l['queue']['position']-l['target'])<.3 for l in s['lines']), ('stale queued target',s)
 assert [l['i'] for l in s['lines'] if l['active']]==s['hot'], ('active class differs',s)
 assert all(s['lines'][i]['mounted'] for i in s['hot']), ('active row hidden',s)

async def main():
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(OUT/'synthetic.wav'),'-codec:a','libmp3lame','-b:a','64k',str(OUT/'seek-synthetic.mp3')],check=True)
 results={'url':BASE,'browser':'Chromium (no Safari)','cases':{},'page_errors':[]};failures=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  for name,w,h,touch in [('desktop',1280,900,False),('landscape',1024,768,True),('portrait',768,1024,True),('narrow',390,844,True)]:
   page=await browser.new_page(viewport={'width':w,'height':h},has_touch=touch,is_mobile=touch,device_scale_factor=2 if touch else 1)
   page.on('pageerror',lambda e:results['page_errors'].append(str(e)))
   await page.goto(BASE);await page.wait_for_function('window.player!==undefined')
   await page.evaluate('player.state.autoPlay=false;player.getBackground().setStaticMode(true)')
   await page.locator('#musicFile').set_input_files(str(OUT/'seek-synthetic.mp3'))
   await page.wait_for_function('player.getAudio().duration>59 && player.getAudio().duration<62')
   await upload(page,ORDERED)
   try:
    samples=[]
    for t in [42,3,48,6,54,0,30,3,57,0]:
     await page.evaluate('(t)=>player.seekAudio(t)',t);await frames(page)
     s=await page.evaluate(SNAP);geometry(s)
     assert s['hot']==[int(t/3)] and s['anchor']==int(t/3),s
     samples.append({'time':t,'hot':s['hot'],'mounted':len([l for l in s['lines'] if l['mounted']])})
    await page.wait_for_timeout(1200);geometry(await page.evaluate(SNAP))
    results['cases'][name+'_rapid_bidirectional']=samples
   except AssertionError as e: failures.append({'case':name+'_rapid_bidirectional','detail':str(e)})
   try:
    await page.evaluate('player.getAudio().play()')
    for t in [45,6,42,3,54,0]:
     await page.evaluate('(t)=>player.seekAudio(t)',t);await frames(page)
     s=await page.evaluate(SNAP);geometry(s)
     assert s['hot']==[int(t/3)] and s['anchor']==int(t/3),s
     assert not (await state(page))['paused']
    results['cases'][name+'_playing_bidirectional']=True
   except AssertionError as e: failures.append({'case':name+'_playing_bidirectional','detail':str(e)})
   finally: await page.evaluate('player.getAudio().pause()')
   # A queued pre-seek spring must not replay after a forced drag/re-entry.
   try:
    await page.evaluate('player.seekAudio(3)');await page.wait_for_timeout(1000)
    await page.evaluate('''()=>{const lp=player.getLyricPlayer(),l=lp.currentLyricLineObjects[2];const top=lp.targetTop.get(l);l.setTransform(top+200,100,1,0,false,.2);l.setTransform(top,100,1,0,true,0)}''')
    await page.wait_for_timeout(700);geometry(await page.evaluate(SNAP))
    results['cases'][name+'_forced_reset_clears_old_target']=True
   except AssertionError as e: failures.append({'case':name+'_forced_reset_clears_old_target','detail':str(e)})
   await upload(page,UNORDERED)
   try:
    s=await page.evaluate(SNAP)
    assert [(l['start'],l['end'],l['text']) for l in s['lines']]==EXPECTED,s
    for delay in [0,1250,-1000]:
     await page.evaluate('(d)=>player.applyLyricDelay(d)',delay)
     for t in [0,3,9,3,12,6,15,25,3,0]:
      await page.evaluate('(t)=>player.seekAudio(t)',t);await frames(page)
      s=await page.evaluate(SNAP);geometry(s)
      expected=[i for i,(a,b,_) in enumerate(EXPECTED) if a<=s['time']<b]
      assert s['hot']==expected,(s,expected)
      expected_anchor=min(expected) if expected else next((i for i,(a,_,_) in enumerate(EXPECTED) if a>=s['time']),len(EXPECTED)-1)
      assert s['anchor']==expected_anchor,s
    results['cases'][name+'_unordered_duplicates_delay_boundaries']=True
   except AssertionError as e: failures.append({'case':name+'_unordered_duplicates_delay_boundaries','detail':str(e)})
   # Single taps toggle playback without seeking; double/drag seek once while paused.
   await page.evaluate('player.applyLyricDelay(0);player.seekAudio(0)')
   await upload(page,ORDERED);await watch(page)
   try:
    line=page.locator('[aria-label^="Seek to Synthetic line 01."]')
    if touch: await line.tap()
    else: await line.click()
    assert (await state(page))['time']==0
    await page.wait_for_timeout(400)
    assert not (await state(page))['paused']
    await page.locator('#playPauseBtn').click()
    if touch:
     await line.tap();box=await line.bounding_box();await page.touchscreen.tap(box['x']+box['width']/2,box['y']+box['height']/2)
    else: await line.dblclick(delay=80)
    await frames(page);geometry(await page.evaluate(SNAP))
    assert (await counts(page))=={'commits':[3000],'seeks':1}
    for dy in [-100,100,-100]:
     await page.evaluate('window.commits=[];window.seeks=0')
     g=await begin(page,touch,dy=dy,start_fraction=.5);c=await candidate(page)
     assert c['visible'] and c['seconds'] is not None,c
     assert await counts(page)=={'commits':[],'seeks':0}
     await end(page,g);geometry(await page.evaluate(SNAP))
     assert await counts(page)=={'commits':[c['start']],'seeks':1}
     assert abs((await state(page))['time']-c['seconds'])<.01
    # Playback crossing a sentence during a held manual drag must not move the anchor.
    await page.evaluate('player.getLyricPlayer().setDragSeekEnabled(false);player.seekAudio(3)')
    await frames(page);g=await begin(page,touch,dy=-80,start_fraction=.5)
    before=await page.evaluate(SNAP)
    await page.evaluate('player.getLyricPlayer().setCurrentTime(12000)');await frames(page)
    after=await page.evaluate(SNAP)
    assert [l['target'] for l in after['lines']]==[l['target'] for l in before['lines']]
    assert not (await state(page))['following']
    await end(page,g)
    results['cases'][name+'_input_and_manual_hold']=True
   except AssertionError as e: failures.append({'case':name+'_input_and_manual_hold','detail':str(e)})
   await page.screenshot(path=str(OUT/f'seek-order-{name}.png'))
   print(name+' completed',flush=True)
   await page.close()
  await browser.close()
 results['failures']=failures
 (OUT/os.environ.get('SEEK_RESULT','seek-order-results.json')).write_text(json.dumps(results,indent=2))
 print(json.dumps({'cases_passed':len(results['cases']),'failures':[f['case'] for f in failures],'page_errors':results['page_errors']}))
 assert not failures and not results['page_errors'], 'See test-results/seek-order-results.json (or SEEK_RESULT)'
if __name__=='__main__':asyncio.run(main())
