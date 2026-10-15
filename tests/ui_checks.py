"""MP3/LRC import and screenshot/layout checks in Chromium only."""
import asyncio,json,re,subprocess
from pathlib import Path
from playwright.async_api import async_playwright
from browser import OUT,BASE,state
from drag_seek import begin,end,candidate,watch,counts

LRC='\n'.join(f'[{i*3//60:02}:{i*3%60:02}.00]'+ ('supercalifragilisticexpialidocious is a deliberately long test word.' if i==1 else f'Synthetic English practice sentence {i+1}. Read this sentence with a clear voice.') for i in range(20))

async def main():
 subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-i',str(OUT/'synthetic.wav'),'-codec:a','libmp3lame','-b:a','64k',str(OUT/'synthetic.mp3')],check=True)
 result={};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox','--autoplay-policy=no-user-gesture-required'])
  for name,w,h,touch in [('desktop',1280,900,False),('landscape',1024,768,True),('portrait',768,1024,True),('narrow',390,844,True),('phone-landscape',844,390,True)]:
   page=await browser.new_page(viewport={'width':w,'height':h},has_touch=touch,is_mobile=touch,device_scale_factor=2 if touch else 1)
   page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(BASE);await page.wait_for_function('window.player!==undefined')
   await page.evaluate('player.state.autoPlay=false;player.getBackground().setStaticMode(true)')
   await page.locator('#musicFile').set_input_files(str(OUT/'synthetic.mp3'))
   await page.wait_for_function('player.getAudio().duration>59 && player.getAudio().duration<62')
   await page.locator('#lyricFile').set_input_files({'name':'synthetic.lrc','mimeType':'text/plain','buffer':LRC.encode()})
   await page.wait_for_function('player.getLyricPlayer().getLyricLines().length===20')
   await page.wait_for_timeout(800)
   # Use actual input, not the application's seek method, on imported MP3/LRC.
   line=page.locator('.speech-lyrics [aria-label^="Seek to supercalifragilisticexpialidocious"]')
   # A single actual click/tap waits out the double-tap window, then resumes/pauses.
   for paused in [False,True]:
    if touch: await line.tap()
    else: await line.click()
    await page.wait_for_timeout(100)
    assert (await state(page))['paused'] != paused
    await page.wait_for_timeout(300)
    assert (await state(page))['paused'] == paused
   await page.evaluate('player.seekAudio(0)');await page.wait_for_timeout(500)
   if touch:
    await line.tap();box=await line.bounding_box()
    await page.touchscreen.tap(box['x']+box['width']/2,box['y']+box['height']/2)
   else: await line.dblclick(delay=80)
   await page.wait_for_timeout(300)
   st=await state(page);assert 1 in st['hot'] and st['paused'],st
   assert abs(st['time']-3)<.01,st
   # Confirm real decoded MP3 playback advances with the imported LRC, then preserve pause.
   await page.locator('#playPauseBtn').click()
   await page.wait_for_timeout(350)
   assert (await state(page))['time']>3.05
   await page.locator('#playPauseBtn').click()
   await page.evaluate('player.seekAudio(3)');await page.wait_for_timeout(500)
   layout=await page.evaluate('''()=>{
     const controls=['#openPracticeAudio','#openPracticeLyrics','#dragSeekMode','#practiceToolbar a','#playPauseBtn','#albumCoverContainer'];
     const boxes=controls.map(selector=>{const el=document.querySelector(selector),r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {selector,x:r.x,y:r.y,w:r.width,h:r.height,unobstructed:!!hit&&(hit===el||el.contains(hit))}});
     const lp=player.getLyricPlayer();const main=lp.currentLyricLineObjects[1].getElement().children[0];
     return {controls:boxes,viewport:{w:innerWidth,h:innerHeight},longText:{scroll:main.scrollWidth,client:main.clientWidth},mounted:lp.getElement().querySelectorAll('[role=button]').length,bodyWidth:document.documentElement.scrollWidth}
   }''')
   await page.screenshot(path=str(OUT/f'ui-{name}.png'))
   for b in layout['controls']:
    assert b['x']>=0 and b['y']>=0 and b['x']+b['w']<=w+1 and b['y']+b['h']<=h+1,(name,b)
    assert b['unobstructed'],(name,b)
   assert layout['longText']['scroll']<=layout['longText']['client']+1,(name,layout['longText'])
   assert layout['bodyWidth']<=w+1,(name,layout['bodyWidth'])
   if h>w:
    overlap=await page.evaluate("(()=>{const a=document.getElementById('albumSidePanel').getBoundingClientRect(),t=document.getElementById('practiceHint').getBoundingClientRect(),l=document.getElementById('lyricsPanel').getBoundingClientRect();return {headerClear:a.y>=t.bottom+4,lyricsClear:l.y>=a.bottom}})()")
    assert overlap['headerClear'] and overlap['lyricsClear'],(name,overlap)
    layout['portrait_spacing']=overlap
   assert layout['mounted']>1
   await watch(page)
   g=await begin(page,touch,dy=-120)
   preview=await candidate(page)
   assert preview['visible'] and preview['seconds'] is not None,(name,preview)
   assert re.fullmatch(r'\d{2,}:\d{2}\.\d{3}',preview['label']),preview
   assert abs(float(preview['label'].split(':')[0])*60+float(preview['label'].split(':')[1])-preview['seconds'])<.001,preview
   badge=await page.locator('.drag-seek-label').evaluate('''e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return {x:r.x,y:r.y,w:r.width,h:r.height,bg:s.backgroundColor,color:s.color,opacity:s.opacity,playerOpacity:getComputedStyle(document.querySelector('.speech-lyrics')).opacity}}''')
   alpha=float(badge['bg'].split(',')[-1].rstrip(')'))
   assert 0<alpha<1 and badge['color']=='rgb(255, 255, 255)' and badge['opacity']=='1' and badge['playerOpacity']=='1',badge
   assert 0<=badge['x'] and badge['x']+badge['w']<=w and 0<=badge['y'] and badge['y']+badge['h']<=h and badge['w']<160,badge
   await page.screenshot(path=str(OUT/f'ui-drag-{name}.png'))
   assert (await state(page))['time']==3
   assert (await counts(page))=={'commits':[],'seeks':0}
   await end(page,g)
   st=await state(page)
   assert st['paused'] and abs(st['time']-preview['seconds'])<.01,(name,st,preview)
   assert (await counts(page))=={'commits':[preview['start']],'seeks':1}
   await page.wait_for_timeout(400)
   assert (await state(page))['paused']
   assert (await counts(page))=={'commits':[preview['start']],'seeks':1}
   layout['mp3_lrc_single_double_tap_and_drag_seek']=True
   layout['drag_time_badge']=badge
   result[name]=layout
   await page.close()
  await browser.close()
 assert not errors,errors
 result['page_errors']=errors
 (OUT/'ui-results.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2))
if __name__=='__main__':asyncio.run(main())
