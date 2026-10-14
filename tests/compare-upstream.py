"""Optional reproducible comparison against the reviewed upstream served on port 5174."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright
async def main():
 result={}
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',headless=True,args=['--no-sandbox'])
  for name,url in [('upstream','http://localhost:5174/'),('fixed',os.environ.get('PLAYER_URL','http://localhost:5173/'))]:
   page=await browser.new_page(viewport={'width':1024,'height':768},device_scale_factor=2,has_touch=True)
   await page.goto(url);await page.wait_for_function('window.player!==undefined')
   await page.evaluate('player.getBackground().setStaticMode(true);player.state.autoPlay=false')
   if name=='fixed': await page.locator('#dragSeekMode').click() # Compare manual browsing in both versions.
   await page.locator('#musicFile').set_input_files('test-results/synthetic.wav')
   await page.wait_for_function('player.getAudio().duration===60')
   await page.evaluate('''()=>{const p=player;p.hasLyrics=true;p.originalLyricLines=Array.from({length:2000},(_,i)=>({startTime:i*3000,endTime:(i+1)*3000,words:[{word:`Synthetic sentence ${i+1}. Practice clearly.`,startTime:i*3000,endTime:(i+1)*3000,obscene:false}],translatedLyric:'',romanLyric:'',isBG:false,isDuet:false}));p.updateLyricsDisplay();p.updateLyricAreaHint();}''')
   await page.wait_for_timeout(1500)
   result[name]=await page.evaluate('''async()=>{const lp=player.getLyricPlayer();let times=[];let calls=0;for(const l of lp.currentLyricLineObjects){const update=l.update.bind(l);l.update=(...a)=>{calls++;return update(...a)}}
     for(let i=0;i<120;i++){await new Promise(requestAnimationFrame);const t=performance.now();lp.update(16.667);times.push(performance.now()-t)}
     times.sort((a,b)=>a-b);const c=player.getBackground().getElement();const before=calls;lp.update(16.667);return {lines:lp.currentLyricLineObjects.length,lineUpdateCallsPerFrame:calls-before,updateMedianMs:times[60],updateP95Ms:times[114],background:{width:c.width,height:c.height}}}''')
   # Hold manual scroll while a playback sentence transition arrives.
   lp=page.locator('.amll-lyric-player');box=await lp.bounding_box();x=box['x']+box['width']/2;y=box['y']+box['height']*.6
   result[name]['inputTarget']=await page.evaluate('p=>({box:p,target:document.elementFromPoint(p.x,p.y)?.outerHTML.slice(0,200)})',{'x':x,'y':y})
   cdp=await page.context.new_cdp_session(page)
   await cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':x,'y':y}]})
   for i in range(1,11):
    await cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y-i*10}]});await page.wait_for_timeout(25)
   await page.wait_for_timeout(300)
   result[name]['gestureState']=await page.evaluate('''()=>({manual:player.getLyricPlayer().manual,following:player.getLyricPlayer().isFollowing,anchor:player.getLyricPlayer().manualAnchor,offset:player.getLyricPlayer().scrollOffset,pointer:player.getLyricPlayer().pointer && {id:player.getLyricPlayer().pointer.id,y:player.getLyricPlayer().pointer.y}})''')
   a=await page.evaluate('player.getLyricPlayer().currentLyricLineObjects[3].getElement().getBoundingClientRect().y')
   await page.evaluate('player.getLyricPlayer().setCurrentTime(9000)')
   await page.wait_for_timeout(500)
   b=await page.evaluate('player.getLyricPlayer().currentLyricLineObjects[3].getElement().getBoundingClientRect().y')
   result[name]['manualTransitionDeltaPx']=b-a
   await cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
   await page.close()
  await browser.close()
 Path('test-results/comparison.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
asyncio.run(main())
