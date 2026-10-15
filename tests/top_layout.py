"""Header/lyric overlap and rotation regression; synthetic media, Chromium only."""
import asyncio,json
from playwright.async_api import async_playwright
from browser import load,OUT
from drag_seek import watch,begin,end,counts,candidate,reset

VIEWPORTS=[('desktop',1280,900),('tablet-landscape',1024,768),
 ('tablet-portrait',768,1024),('wide-tablet-portrait',820,1180),
 ('phone-portrait',390,844),('phone-landscape',844,390),
 ('short-tablet',1024,712),('reference-size',1536,1067)]

async def layout(page):
 return await page.evaluate('''()=>{
  const box=e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom}};
  const lp=player.getLyricPlayer(),el=lp.getElement(),panel=document.querySelector('#lyricsPanel');
  const controls=['#practiceToolbar','#practiceHint','#localSavePanel summary'].map(s=>box(document.querySelector(s)));
  const bottom=Math.max(...controls.map(r=>r.bottom));
  const hits=[];
  for(let x=20;x<innerWidth;x+=40)for(let y=5;y<bottom;y+=10){
   if(document.elementsFromPoint(x,y).some(e=>e===el||el.contains(e)))hits.push({x,y});
  }
  const active=lp.currentLyricLineObjects[5].getElement();
  const r=active.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
  const toolbar=getComputedStyle(document.querySelector('#practiceToolbar'));
  return {controls,headerBottom:bottom,panel:box(panel),lyrics:box(el),headerLyricHits:hits,
   active:box(active),activeHittable:!!hit&&(hit===active||active.contains(hit)),
   bodyWidth:document.documentElement.scrollWidth,viewport:{w:innerWidth,h:innerHeight},
   toolbar:{background:toolbar.backgroundColor,image:toolbar.backgroundImage,mask:toolbar.maskImage}};
 }''')

async def main():
 results={};errors=[]
 async with async_playwright() as p:
  browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
  page=await browser.new_page(viewport={'width':1024,'height':768},has_touch=True,is_mobile=True)
  page.on('pageerror',lambda e:errors.append(str(e)))
  await load(page);await watch(page)
  # The same loaded page rotates and changes layout; no reload hides stale geometry.
  for name,w,h in VIEWPORTS:
   await page.set_viewport_size({'width':w,'height':h})
   await reset(page,time=15)
   for inset in [10,34]:
    # Inject a nonzero resolved inset: this checks CSS layout, not iPad OS behavior.
    await page.evaluate('(v)=>document.documentElement.style.setProperty("--practice-top",v+"px")',inset)
    await page.wait_for_timeout(600)
    data=await layout(page)
    assert data['lyrics']['y']>=data['headerBottom']+4,(name,inset,data)
    assert not data['headerLyricHits'],(name,inset,data)
    assert data['lyrics']['bottom']<=h+1 and data['bodyWidth']<=w+1,(name,inset,data)
    assert data['active']['y']>=data['lyrics']['y']-1,(name,inset,data)
    assert data['active']['bottom']<=data['lyrics']['bottom']+1 and data['activeHittable'],(name,inset,data)
    assert data['toolbar']=={'background':'rgba(0, 0, 0, 0)','image':'none','mask':'none'},data
    results[f'{name}-inset-{inset}']=data
   await page.evaluate('document.documentElement.style.removeProperty("--practice-top")')
   await page.wait_for_timeout(300)
   await page.screenshot(path=str(OUT/f'top-layout-{name}.png'))
  # A touch drag that leaves the transcript into the header must cancel its seek.
  await page.set_viewport_size({'width':1024,'height':768});await reset(page,time=15)
  g=await begin(page,True,dy=-100)
  assert (await candidate(page))['visible']
  await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':g['x'],'y':30,'id':0}]})
  await end(page,g)
  assert (await counts(page))=={'commits':[],'seeks':0}
  assert not (await candidate(page))['visible']
  results['drag_into_header_cancels_seek']=True
  await browser.close()
 assert not errors,errors
 results['page_errors']=errors
 (OUT/'top-layout-results.json').write_text(json.dumps(results,indent=2))
 print(f'PASS: {len(VIEWPORTS)} rotating viewports × 2 resolved top insets; header exit cancels seek; no page errors')

if __name__=='__main__':asyncio.run(main())
