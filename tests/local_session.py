"""Real Chromium IndexedDB + persistent browser restart, synthetic media only.
Quota/unavailability/abort failures are injected; this is not physical iPad Safari.
"""
import asyncio, base64, hashlib, json, os, shutil, subprocess
from pathlib import Path
from playwright.async_api import async_playwright
from browser import OUT, BASE

LRC = '[00:06.00]Third\n[00:00.00]First\n[00:03.00]Second'
RESULT = {'cases': {}, 'page_errors': [], 'non_read_requests': []}
MP3 = b''


def record(name, value=True):
    RESULT['cases'][name] = value
    print('PASS', name, flush=True)


async def ready(page):
    await page.wait_for_function('window.player')
    await page.evaluate('player.localRestoreReady')
    await page.evaluate('player.state.autoPlay=false;player.getBackground().setStaticMode(true)')


async def phase(page, expected):
    await page.wait_for_function('phase=>document.getElementById("localSavePanel").dataset.phase===phase', arg=expected)


async def stored(page):
    return await page.evaluate('''async()=>{
      const saved=await player.localMemory.backend.read();
      if(!saved)return null;
      const {media,progress}=saved;
      return {id:media.id,audio:media.audio?.name,size:media.audio?.blob.size,
        captions:media.captions?.name,text:media.captions?.text,position:progress.position,delay:progress.delay};
    }''')


async def current(page):
    return await page.evaluate('''()=>({audio:player.selectedMusicFile?.name,captions:player.selectedLyricFile?.name,
      position:player.getAudio().currentTime,paused:player.getAudio().paused,delay:player.state.lyricDelay,
      lines:player.getLyricPlayer().getLyricLines().map(l=>l.words.map(w=>w.word).join(''))})''')


async def import_audio(page, name='lesson-A.MP3'):
    await page.locator('#musicFile').set_input_files({'name': name, 'mimeType': 'application/octet-stream', 'buffer': MP3})
    await page.wait_for_function('name=>player.selectedMusicFile?.name===name && player.getAudio().duration>59', arg=name)


async def import_captions(page, name='lesson-A.LRC', text=LRC):
    await page.locator('#lyricFile').set_input_files({'name': name, 'mimeType': 'text/plain', 'buffer': text.encode()})
    await page.wait_for_function('name=>player.selectedLyricFile?.name===name', arg=name)


async def panel_action(page, selector):
    if not await page.locator('#localSavePanel').evaluate('e=>e.open'):
        await page.locator('#localSavePanel summary').click()
    await page.locator(selector).click()


async def install_observers(context):
    await context.add_init_script('''window.playAttempts=[];
      const originalPlay=HTMLMediaElement.prototype.play;
      HTMLMediaElement.prototype.play=function(){playAttempts.push(this.src);return originalPlay.call(this)};''')
    context.on('page', lambda page: page.on('pageerror', lambda e: RESULT['page_errors'].append(str(e))))
    context.on('request', lambda request: RESULT['non_read_requests'].append({'method': request.method, 'url': request.url}) if request.method not in ['GET', 'HEAD'] else None)


async def main():
    global MP3
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(OUT/'synthetic.wav'), '-codec:a', 'libmp3lame', '-b:a', '64k', str(OUT/'remember.mp3')], check=True)
    MP3 = (OUT/'remember.mp3').read_bytes()
    profile = OUT/'synthetic-session-profile'
    if profile.exists(): shutil.rmtree(profile)
    async with async_playwright() as p:
        options = {'executable_path': os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), 'headless': True, 'args': ['--no-sandbox'],
                   'viewport': {'width': 768, 'height': 1024}, 'has_touch': True, 'is_mobile': True}
        context = await p.chromium.launch_persistent_context(str(profile), **options)
        await install_observers(context)
        page = await context.new_page()
        await page.goto(BASE); await ready(page); await phase(page, 'empty')
        await import_audio(page); await import_captions(page); await phase(page, 'saved')
        value = await stored(page)
        assert value['audio'] == 'lesson-A.MP3' and value['text'] == LRC and value['size'] == len(MP3), value
        assert await page.locator('#musicFile').get_attribute('accept') is None
        assert await page.locator('#lyricFile').get_attribute('accept') is None
        record('blob_and_captions_committed')
        await page.evaluate('player.applyLyricDelay(750);player.seekAudio(12.345)')
        await page.wait_for_function('player.localMemory.lastProgress==="12.345:750"')
        await page.reload(); await ready(page); await phase(page, 'saved')
        state = await current(page)
        assert state['audio'] == 'lesson-A.MP3' and state['captions'] == 'lesson-A.LRC', state
        assert state['paused'] and abs(state['position']-12.345) < .03 and state['delay'] == 750, state
        assert state['lines'] == ['First', 'Second', 'Third']
        assert await page.evaluate('playAttempts') == []
        digest = await page.evaluate('''async()=>{
          const bytes=await (await fetch(player.getAudio().src)).arrayBuffer();
          return [...new Uint8Array(await crypto.subtle.digest('SHA-256',bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
        }''')
        assert digest == hashlib.sha256(MP3).hexdigest()
        record('refresh_restores_exact_blob_captions_offset_position_paused')
        # A real user click resumes; progress writes do not rewrite the audio Blob.
        await page.evaluate('''()=>{
          window.storageWrites={files:0,progress:0};
          const db=player.localMemory.backend,write=db.write.bind(db),progress=db.progress.bind(db);
          db.write=(...args)=>{storageWrites.files++;return write(...args)};
          db.progress=(...args)=>{storageWrites.progress++;return progress(...args)};
        }''')
        await page.locator('#playPauseBtn').click()
        await page.wait_for_function('!player.getAudio().paused')
        await page.wait_for_timeout(4600)
        counts = await page.evaluate('storageWrites')
        assert counts['files'] == 0 and 1 <= counts['progress'] <= 3, counts
        before_reload = (await current(page))['position']
        await page.reload(); await ready(page)
        state = await current(page)
        assert state['paused'] and abs(state['position']-before_reload) < .5, (state, before_reload)
        assert await page.evaluate('playAttempts') == []
        record('playing_refresh_checkpoint_and_throttled_small_progress', counts)
        await context.close()
        # Close the browser, then reuse its on-disk profile (not a localStorage-only export).
        context = await p.chromium.launch_persistent_context(str(profile), **options)
        await install_observers(context)
        page = await context.new_page(); await page.goto(BASE); await ready(page)
        state = await current(page)
        assert state['paused'] and state['audio'] == 'lesson-A.MP3' and abs(state['position']-before_reload) < .5, state
        assert await page.evaluate('playAttempts') == []
        record('closed_browser_reopened_with_full_session')

        # Replacing audio clears the old caption association and resets position.
        await import_audio(page, 'lesson-B.MP3'); await phase(page, 'saved')
        value = await stored(page)
        assert value['audio'] == 'lesson-B.MP3' and not value.get('captions') and value['position'] < .1, value
        assert (await current(page))['lines'] == []
        await import_captions(page, 'lesson-B.LRC', '[00:00.00]New lesson'); await phase(page, 'saved')
        await page.reload(); await ready(page)
        assert (await current(page))['lines'] == ['New lesson']
        record('replacement_resets_position_and_does_not_pair_old_captions')

        # Failed transactions preserve the previous whole pair, with no saved claim.
        prior = await stored(page)
        await page.evaluate('''()=>{window.originalPut=IDBObjectStore.prototype.put;
          IDBObjectStore.prototype.put=function(...args){if(this.name==='media')throw new DOMException('Synthetic quota','QuotaExceededError');return originalPut.apply(this,args)}}''')
        await import_audio(page, 'quota.MP3'); await phase(page, 'error')
        message = await page.locator('#localSaveStatus').text_content()
        assert '空間不足' in message, message
        assert await stored(page) == prior
        await page.evaluate('()=>{IDBObjectStore.prototype.put=originalPut}')
        await panel_action(page, '#saveLocalSession'); await phase(page, 'saved')
        assert (await stored(page))['audio'] == 'quota.MP3'
        await page.locator('#localSavePanel summary').click()
        record('quota_failure_atomicity_and_explicit_retry')
        await page.evaluate('''()=>{IDBObjectStore.prototype.put=function(...args){
          if(this.name==='progress')throw new DOMException('Synthetic progress quota','QuotaExceededError');
          return originalPut.apply(this,args);
        };player.seekAudio(9)}''')
        await phase(page, 'error')
        assert '空間不足' in await page.locator('#localSaveStatus').text_content()
        await page.evaluate('()=>{IDBObjectStore.prototype.put=originalPut}')
        await panel_action(page, '#saveLocalSession'); await phase(page, 'saved')
        await page.locator('#localSavePanel summary').click()
        record('progress_callback_write_failure_has_no_uncaught_error')
        prior = await stored(page)
        await page.evaluate('''()=>{IDBObjectStore.prototype.put=function(...args){
          const req=originalPut.apply(this,args);
          if(this.name==='media'){const tx=this.transaction;req.addEventListener('success',()=>tx.abort())}
          return req;
        }}''')
        await import_captions(page, 'abort.LRC'); await phase(page, 'error')
        assert await stored(page) == prior
        await page.evaluate('()=>{IDBObjectStore.prototype.put=originalPut}')
        record('request_success_followed_by_abort_is_not_saved')

        # Hold an actual backend write, then clear it while it is in flight.
        await page.evaluate('''()=>{
          const db=player.localMemory.backend;window.originalWrite=db.write.bind(db);
          const gate=new Promise(resolve=>window.releaseSave=resolve);
          db.write=async value=>{window.writeStarted=true;await gate;return originalWrite(value)};
        }''')
        await import_audio(page, 'pending.MP3'); await page.wait_for_function('window.writeStarted')
        await phase(page, 'saving')
        await panel_action(page, '#clearLocalSession'); await phase(page, 'clearing')
        await page.evaluate('releaseSave()'); await phase(page, 'cleared')
        assert await stored(page) is None
        await page.evaluate('player.seekAudio(20);player.localMemory.checkpoint()')
        await page.wait_for_timeout(2200)
        assert await stored(page) is None
        await page.reload(); await ready(page); await phase(page, 'empty')
        assert not (await current(page)).get('audio')
        record('clear_wins_inflight_save_no_resurrection_on_seek_or_reload')

        # Caption-first imports keep their association with the first audio.
        await import_captions(page, 'first.LRC'); await phase(page, 'saved')
        await page.reload(); await ready(page)
        assert not (await current(page)).get('audio') and (await current(page))['lines'] == ['First', 'Second', 'Third']
        await import_audio(page, 'first.MP3'); await phase(page, 'saved')
        assert (await stored(page))['captions'] == 'first.LRC'
        record('caption_only_restore_then_first_audio_pair')
        # Captions selected while audio validates wait for that same audio import.
        await page.evaluate('''async data=>{
          const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
          const a=player.loadMusicFromFile(new File([bytes],'concurrent.MP3'));
          const c=player.loadLyricFromFile(new File(['[00:00.00]Concurrent'],'concurrent.LRC'));
          await Promise.all([a,c]);
        }''', base64.b64encode(MP3).decode())
        await phase(page, 'saved')
        value = await stored(page)
        assert value['audio'] == 'concurrent.MP3' and value['captions'] == 'concurrent.LRC', value
        record('simultaneous_audio_and_captions_pair')
        await page.evaluate('''async data=>{
          const slow=new File(['x'],'stale.LRC');let release;slow.text=()=>new Promise(resolve=>release=resolve);
          const pending=player.loadLyricFromFile(slow);
          const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
          await player.loadMusicFromFile(new File([bytes],'newer.MP3'));
          release('[00:00.00]Wrong pair');await pending;
        }''', base64.b64encode(MP3).decode())
        await phase(page, 'saved')
        assert not (await stored(page)).get('captions') and (await current(page))['lines'] == []
        record('stale_caption_read_cannot_pair_with_new_audio')

        # A slow startup read cannot overwrite a manual choice made meanwhile.
        await page.evaluate('''async()=>{
          window.olderSaved=await player.localMemory.read();
          const originalRead=player.localMemory.read.bind(player.localMemory);
          player.localMemory.read=()=>new Promise(resolve=>window.releaseRead=()=>{player.localMemory.read=originalRead;resolve(olderSaved)});
          window.pendingRestore=player.restoreLocalSession();
        }''')
        await import_audio(page, 'manual-newest.MP3'); await phase(page, 'saved')
        await page.evaluate('releaseRead();pendingRestore')
        assert (await current(page))['audio'] == 'manual-newest.MP3'
        assert (await stored(page))['audio'] == 'manual-newest.MP3'
        record('late_restore_read_cannot_override_manual_import')

        # Clear failure is visible and leaves the actual record intact.
        await page.evaluate('''()=>{window.originalDelete=IDBObjectStore.prototype.delete;
          IDBObjectStore.prototype.delete=function(key){if(key==='last')throw new DOMException('Synthetic unavailable','SecurityError');return originalDelete.call(this,key)}}''')
        prior = await stored(page)
        await panel_action(page, '#clearLocalSession'); await phase(page, 'error')
        assert '未能清除' in await page.locator('#localSaveStatus').text_content()
        assert await stored(page) == prior
        await page.evaluate('()=>{IDBObjectStore.prototype.delete=originalDelete}')
        await panel_action(page, '#clearLocalSession'); await phase(page, 'cleared')
        assert await stored(page) is None
        record('clear_failure_is_not_reported_as_cleared')

        # Structurally damaged data and a damaged Blob are recoverable via clear.
        for corrupt in ['shape', 'audio', 'captions']:
            await page.evaluate('''async kind=>{
              const db=await player.localMemory.backend.open();
              await new Promise((resolve,reject)=>{
                const tx=db.transaction(['media','progress'],'readwrite');
                const audio={blob:kind==='shape'?'broken':new Blob(['invalid audio']),name:'broken.MP3',type:'audio/mpeg',lastModified:1};
                const captions=kind==='captions'?{text:'not timed',name:'broken.LRC',type:'',lastModified:1}:null;
                tx.objectStore('media').put({version:1,id:'damaged',audio:kind==='captions'?null:audio,captions},'last');
                tx.oncomplete=resolve;tx.onabort=()=>reject(tx.error);
              });
            }''', corrupt)
            await page.reload(); await ready(page); await phase(page, 'error')
            assert (await current(page))['paused'] and await page.evaluate('playAttempts') == []
            await panel_action(page, '#clearLocalSession'); await phase(page, 'cleared')
            record('corrupt_'+corrupt+'_shows_error_and_can_clear')

        # The control remains readable and usable on desktop/tablet/phone sizes.
        await import_audio(page); await import_captions(page); await phase(page, 'saved')
        for name,w,h in [('desktop',1280,900),('tablet-landscape',1024,768),('tablet-portrait',768,1024),('phone',390,844),('phone-landscape',844,390)]:
            await page.set_viewport_size({'width': w, 'height': h})
            await page.wait_for_timeout(350)
            await page.locator('#localSavePanel').evaluate('e=>e.open=true')
            layout = await page.evaluate('''()=>['#localSavePanel summary','#localSavePanel .save-details','#saveLocalSession','#clearLocalSession'].map(selector=>{
              const el=document.querySelector(selector),r=el.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);
              return {selector,x:r.x,y:r.y,w:r.width,h:r.height,hit:!!hit&&(hit===el||el.contains(hit))};
            })''')
            for box in layout:
                assert box['x']>=0 and box['y']>=0 and box['x']+box['w']<=w+1 and box['y']+box['h']<=h+1 and box['hit'], (name,box)
                if 'Session' in box['selector'] or 'summary' in box['selector']: assert box['h']>=44
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.screenshot(path=str(OUT/f'storage-{name}.png'))
            record('storage_ui_'+name)
            await page.locator('#localSavePanel').evaluate('e=>e.open=false')
        await context.close()

        browser = await p.chromium.launch(executable_path=options['executable_path'], args=['--no-sandbox'])
        unavailable = await browser.new_context()
        await install_observers(unavailable)
        await unavailable.add_init_script('''Object.defineProperty(window,'indexedDB',{get(){throw new DOMException('Synthetic blocked storage','SecurityError')}})''')
        page = await unavailable.new_page(); await page.goto(BASE); await ready(page); await phase(page, 'error')
        await import_audio(page); await import_captions(page); await phase(page, 'error')
        assert (await current(page))['lines'] == ['First','Second','Third']
        await page.locator('#playPauseBtn').click(); await page.wait_for_function('!player.getAudio().paused')
        record('unavailable_storage_does_not_break_manual_import_or_playback')
        await browser.close()
    assert not RESULT['page_errors'], RESULT['page_errors']
    assert not RESULT['non_read_requests'], RESULT['non_read_requests']
    RESULT['limits'] = 'Chromium Linux and touch/viewport emulation; no physical iPad, Safari/WebKit, real disk exhaustion or OS eviction test.'
    (OUT/'local-session-results.json').write_text(json.dumps(RESULT, indent=2))
    print(json.dumps(RESULT, indent=2))


if __name__ == '__main__': asyncio.run(main())
