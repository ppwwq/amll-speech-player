"""Gap-midpoint selection and same-sentence replay using real pointer input.

Synthetic media in Chromium; tablet/phone sizes do not constitute Safari testing.
"""
import asyncio,json,os
from playwright.async_api import async_playwright
from browser import load,state,OUT
from drag_seek import begin,end,candidate,watch,counts,reset

TEXTS=['First short sentence.','A longer sentence about practising clear pronunciation and listening carefully to every word before starting again.',
       'Short third sentence.','Another deliberately long sentence which wraps across several lines when the device is held in portrait orientation.',
       'Short fifth sentence.','The last example sentence.']
LRC='\n'.join(f'[00:{i*8:02}.00]{text}' for i,text in enumerate(TEXTS))

async def snapshot(page):
 return await page.evaluate('''()=>{
  const lp=player.getLyricPlayer(),rows=lp.currentLyricLineObjects.map((l,i)=>{
   const e=l.getElement(),r=e.getBoundingClientRect(),size=lp.lyricLinesSize.get(l);
   return {i,top:lp.targetTop.get(l),height:size?.[1],mounted:e.isConnected,
    y:r.y,h:r.height,scale:new DOMMatrix(getComputedStyle(e).transform).a};
  });
  return {rows,guide:lp.size[1]/2,index:lp.currentLyricLineObjects.indexOf(lp.previewLine),
   target:lp.dragCandidate?.seconds,offset:lp.scrollOffset,clock:lp.currentTime,
   hot:[...lp.hotLines],bounds:lp.getElement().getBoundingClientRect().toJSON()};
 }''')

async def move(page,g,y):
 if g['cdp']:
  await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':g['x'],'y':y,'id':0}]})
 else:await page.mouse.move(g['x'],y)
 g['y']=y
 await page.wait_for_timeout(80)

async def short_gesture(page,touch,dy):
 b=await page.locator('.speech-lyrics').bounding_box()
 x=b['x']+b['width']/2;y=b['y']+b['height']/2
 cdp=await page.context.new_cdp_session(page) if touch else None
 if cdp:await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y,'id':0}]})
 else:await page.mouse.move(x,y);await page.mouse.down()
 g={'cdp':cdp,'x':x,'y':y,'box':b}
 await move(page,g,y+dy)
 return g

async def align_gap(page,g,left,relative):
 # Align an independently observed, unscaled row edge to the visible guide.
 s=await snapshot(page);a,b=s['rows'][left:left+2]
 boundary=(a['top']+a['height']+b['top'])/2
 y=g['y']+s['guide']+relative-boundary
 assert g['box']['y']+2<y<g['box']['y']+g['box']['height']-2,(s,y,g)
 await move(page,g,y)
 return await snapshot(page)

async def main():
 results={'cases':{},'page_errors':[],'limits':'Chromium, synthetic WAV/LRC; no physical iPad or Safari.'}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  # Keep the same loaded tablet page when rotating, exercising cached geometry.
  for mode,touch,sizes in [('mouse',False,[('desktop',1280,900)]),
                           ('touch',True,[('landscape',1024,768),('portrait',768,1024),('phone',390,844)])]:
   page=await browser.new_page(viewport={'width':sizes[0][1],'height':sizes[0][2]},has_touch=touch,is_mobile=touch)
   page.on('pageerror',lambda e:results['page_errors'].append(str(e)))
   await load(page)
   await page.locator('#lyricFile').set_input_files({'name':'replay.lrc','mimeType':'text/plain','buffer':LRC.encode()})
   await page.wait_for_function('player.getLyricPlayer().getLyricLines().length===6')
   await watch(page)
   for name,w,h in sizes:
    await page.set_viewport_size({'width':w,'height':h});await page.wait_for_timeout(500)
    case={}
    # Both sides of the actual space between unequal-height adjacent sentences.
    for left in [1,2]:
     await reset(page,time=left*8+4)
     g=await begin(page,touch,dy=-12,start_fraction=.5)
     samples=[]
     for relative,index in [(2,left),(-2,left+1),(2,left),(-2,left+1)]:
      s=await align_gap(page,g,left,relative)
      assert s['index']==index,(name,left,relative,s)
      initial=s
      await page.wait_for_timeout(650)
      settled=await snapshot(page)
      assert settled['index']==index,(name,left,relative,initial,settled)
      assert [(x['top'],x['height']) for x in settled['rows']]==[(x['top'],x['height']) for x in initial['rows']],(initial,settled)
      assert (await counts(page))=={'commits':[],'seeks':0}
      assert (await state(page))['time']==left*8+4
      samples.append({'relative':relative,'index':index,'heights':[s['rows'][left]['height'],s['rows'][left+1]['height']]})
     final=await candidate(page);await end(page,g)
     assert (await counts(page))=={'commits':[final['start']],'seeks':1}
     case[f'gap_{left}_{left+1}']=samples
    # Replay a half-finished sentence directly, without selecting the previous one.
    for playing in [False,True]:
     replays=[]
     await reset(page,time=12)
     if playing:await page.evaluate('player.getAudio().play()')
     for repeat in range(3):
      # Subsequent gestures run consecutively, without a setup seek/reset.
      await page.evaluate('window.commits=[];window.seeks=0')
      g=await begin(page,touch,dy=18,start_fraction=.5)
      if repeat==1:
       # Pass into the following sentence and return to the current sentence
       # during the same drag, without committing an intermediate target.
       away=await align_gap(page,g,1,-8)
       assert away['index']==2,(name,away)
      s=await snapshot(page)
      # Move the same row's unscaled centre to the guide, if necessary.
      row=s['rows'][1]
      await move(page,g,g['y']+s['guide']-row['top']-row['height']/2)
      s=await snapshot(page)
      assert s['index']==1 and s['hot']==[1],(name,playing,s)
      assert (await counts(page))=={'commits':[],'seeks':0}
      await end(page,g)
      st=await state(page)
      assert (await counts(page))=={'commits':[8000],'seeks':1},(name,playing,st)
      assert st['paused']==(not playing) and 8<=st['time']<8.8,(name,playing,st)
      assert st['hot']==[1] and not st['following'],st
      if not playing:assert st['lyric']==8000,st
      await page.wait_for_timeout(400)
      assert (await counts(page))=={'commits':[8000],'seeks':1}
      assert (await state(page))['paused']==(not playing)
      replays.append(st)
     case[f'same_sentence_playing_{playing}']=replays
    # Exactly 10px remains a tap; the next pixel arms a drag, without an extra tap.
    for dy,drag in [(0,False),(10,False),(11,True)]:
     await reset(page,time=12)
     g=await short_gesture(page,touch,dy)
     assert (await candidate(page))['visible']==drag,(name,dy)
     chosen=await candidate(page);await end(page,g);await page.wait_for_timeout(400)
     st=await state(page)
     if drag:
      assert (await counts(page))=={'commits':[chosen['start']],'seeks':1}
      assert st['paused']
     else:
      assert (await counts(page))=={'commits':[],'seeks':0}
      assert not st['paused'] and st['time']>=12,(name,dy,st)
    case['tap_and_drag_threshold']=True
    # Cancellation while the same row is selected cannot rewind or toggle play.
    for playing in [False,True]:
     await reset(page,time=12)
     if playing:await page.evaluate('player.getAudio().play()')
     g=await begin(page,touch,dy=18,start_fraction=.5)
     if touch:await end(page,g,cancel=True)
     else:
      await page.evaluate('player.getLyricPlayer().getElement().dispatchEvent(new PointerEvent("pointercancel",{pointerId:1}))')
      await end(page,g)
     await page.wait_for_timeout(400)
     assert (await counts(page))=={'commits':[],'seeks':0}
     st=await state(page)
     assert 12<=st['time']<14 and st['paused']==(not playing),st
     assert not (await candidate(page))['visible']
    case['pointercancel_no_seek']=True
    results['cases'][name]=case
    print(name+' passed',flush=True)
   await page.close()
  await browser.close()
 assert not results['page_errors'],results
 (OUT/os.environ.get('REPLAY_RESULT','drag-replay-results.json')).write_text(json.dumps(results,indent=2))
 print('PASS: midpoint boundaries, preview stability, same-sentence replay, thresholds and cancellation')

if __name__=='__main__':asyncio.run(main())
