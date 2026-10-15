"""Native AMLL drag-preview scaling, stable layout, cleanup and reduced motion."""
import asyncio, json
from playwright.async_api import async_playwright
from browser import load, state, OUT
from drag_seek import begin, end, candidate, watch, counts, reset


async def visual(page):
    return await page.evaluate('''()=>{
      const lp=player.getLyricPlayer(), row=lp.previewLine, e=row?.getElement();
      if(!e)return null;
      const s=getComputedStyle(e), main=e.children[0], r=e.getBoundingClientRect();
      const textBox=element=>{const range=document.createRange();range.selectNodeContents(element.children[0]);return range.getBoundingClientRect()};
      const text=textBox(e), container=lp.getElement().getBoundingClientRect();
      const neighbours=[...lp.animated].filter(l=>l!==row&&!l.getLine().isBG).map(l=>textBox(l.getElement()));
      return {index:lp.currentLyricLineObjects.indexOf(row),top:lp.targetTop.get(row),
        size:lp.lyricLinesSize.get(row),scale:new DOMMatrix(s.transform).a,
        spring:row.lineTransforms.scale.getCurrentPosition(),opacity:getComputedStyle(main).opacity,
        outline:s.outlineStyle,bright:s.getPropertyValue('--bright-mask-alpha').trim(),
        dark:s.getPropertyValue('--dark-mask-alpha').trim(),marked:lp.getElement().querySelectorAll('[data-drag-candidate]').length,
        center:r.y+r.height/2,wordOverflow:main.scrollWidth-main.clientWidth,
        textWithinWidth:text.left>=container.left&&text.right<=container.right,
        noTextOverlap:neighbours.every(n=>n.bottom<=text.top||n.top>=text.bottom),
        otherScales:[...lp.animated].filter(l=>l!==row&&!l.getLine().isBG).map(l=>l.lineTransforms.scale.getCurrentPosition()),
        hot:[...lp.hotLines],clock:lp.getCurrentTime()};
    }''')


async def main():
    results={'cases':{},'page_errors':[]}
    async with async_playwright() as p:
        browser=await p.chromium.launch(executable_path='/usr/bin/chromium',args=['--no-sandbox'])
        for name,w,h,touch,reduced in [('desktop',1280,900,False,False),('tablet',768,1024,True,False),
                                     ('phone-wrapped',390,844,True,False),('reduced-motion',768,1024,True,True)]:
            page=await browser.new_page(viewport={'width':w,'height':h},has_touch=touch,is_mobile=touch,
                                        reduced_motion='reduce' if reduced else 'no-preference')
            page.on('pageerror',lambda e:results['page_errors'].append(str(e)))
            await load(page)
            if name=='phone-wrapped':
                text='\n'.join(f'[00:{i*3:02}.00]A deliberately long wrapped sentence {i} about pronunciation and learning to speak clearly.' for i in range(15))
                await page.locator('#lyricFile').set_input_files({'name':'wrapped.lrc','mimeType':'text/plain','buffer':text.encode()})
                await page.wait_for_function('player.getLyricPlayer().getLyricLines().length===15')
            await watch(page);await reset(page)
            initial=await state(page)
            g=await begin(page,touch,dy=-120)
            early=await visual(page);assert early is not None
            await page.wait_for_timeout(650)
            settled=await visual(page);target=await candidate(page)
            assert settled['marked']==1 and settled['index']==early['index'],(early,settled)
            assert settled['size']==early['size'] and abs(settled['top']-early['top'])<.1,(early,settled)
            assert abs(settled['center']-early['center'])<.2,(early,settled)
            assert settled['outline']=='none' and settled['opacity']=='1',settled
            assert settled['bright']=='1' and settled['dark']=='1',settled
            assert settled['wordOverflow']<=1,settled
            assert settled['textWithinWidth'] and settled['noTextOverlap'],settled
            assert all(abs(s-100)<.1 for s in settled['otherScales']),settled
            assert settled['hot']==initial['hot'] and settled['clock']==initial['lyric'],settled
            assert (await state(page))['time']==initial['time'] and (await counts(page))=={'commits':[],'seeks':0}
            if reduced:
                assert settled['scale']==1,settled
            else:
                assert 1.005<early['scale']<settled['scale']<=1.031,(early,settled)
                assert abs(settled['spring']/100-settled['scale'])<.001,settled
            await page.screenshot(path=str(OUT/f'drag-preview-{name}.png'))
            # A second movement replaces the highlighted row, without moving audio.
            if not reduced:
                old_index=settled['index']
                step=min(180,g['y']-g['box']['y']-20)
                if g['cdp']:
                    await g['cdp'].send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':g['x'],'y':g['y']-step,'id':0}]})
                else:
                    await page.mouse.move(g['x'],g['y']-step)
                await page.wait_for_timeout(700)
                later=await visual(page);target=await candidate(page)
                assert later['marked']==1 and later['index']!=old_index,(settled,later)
                assert await page.evaluate('i=>Math.abs(player.getLyricPlayer().currentLyricLineObjects[i].lineTransforms.scale.getCurrentPosition()-100)<.1',old_index)
                assert (await counts(page))=={'commits':[],'seeks':0}
            await end(page,g)
            assert abs((await state(page))['time']-target['seconds'])<.01
            assert (await counts(page))=={'commits':[target['start']],'seeks':1}
            assert await page.locator('[data-drag-candidate]').count()==0
            await reset(page)
            g=await begin(page,touch,dy=-120)
            await page.evaluate('player.getLyricPlayer().cancelPointer()')
            await end(page,g)
            await page.wait_for_timeout(650)
            assert await page.locator('[data-drag-candidate]').count()==0
            assert (await counts(page))=={'commits':[],'seeks':0}
            assert await page.evaluate('()=>[...player.getLyricPlayer().animated].every(l=>Math.abs(l.lineTransforms.scale.getCurrentPosition()-100)<.1)')
            # Keeping keyboard focus styling is independent of pointer preview.
            await page.evaluate('player.getLyricPlayer().currentLyricLineObjects[1].getElement().focus()')
            await page.keyboard.press('Enter')
            focused=await page.evaluate('()=>({visible:document.activeElement.matches(":focus-visible"),outline:getComputedStyle(document.activeElement).outlineStyle})')
            assert focused['visible'] and focused['outline']=='solid',focused
            results['cases'][name]={'early_scale':early['scale'],'settled_scale':settled['scale'],
                                    'stable_layout_no_early_seek':True,'release_once_cancel_cleans':True,'keyboard_focus_retained':True}
            await page.close()
        await browser.close()
    assert not results['page_errors'],results['page_errors']
    results['limits']='Chromium with touch/viewport/reduced-motion emulation; no physical iPad/Safari execution.'
    (OUT/'drag-preview-results.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))


if __name__=='__main__':asyncio.run(main())
