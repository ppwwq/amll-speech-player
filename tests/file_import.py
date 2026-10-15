"""Synthetic local files; native chooser routing + simulated cancel, not iPad Files UI."""
import asyncio, base64, json, os, subprocess
from playwright.async_api import async_playwright
from browser import OUT, BASE, srt

LRC = '[00:06.00]Third\n[00:00.00]First\n[00:03.00]Second'


async def snapshot(page):
    return await page.evaluate('''()=>({
      music:player.state.musicUrl, lyric:player.state.lyricUrl,
      audio:player.selectedMusicFile?.name, captions:player.selectedLyricFile?.name,
      audioDisplay:document.getElementById('musicFileDisplay')?.textContent,
      captionDisplay:document.getElementById('lyricFileDisplay')?.textContent,
      lines:player.getLyricPlayer().getLyricLines().map(l=>l.words.map(w=>w.word).join('')),
      icons:['musicFileBtn','lyricFileBtn'].map(id=>document.querySelector('#'+id+' .uploaded-icon').style.display)
    })''')


async def choose(page, selector, input_id, payload, event='click'):
    print(f'chooser {selector} {event}', flush=True)
    kind = 'audio' if input_id == 'musicFile' else 'captions'
    completed = await page.evaluate('completedImports.'+kind)
    async with page.expect_file_chooser() as pending:
        if event == 'contextmenu':
            await page.locator(selector).click(button='right', force=True)
        elif event == 'hold':
            box = await page.locator(selector).bounding_box()
            await page.mouse.move(box['x']+box['width']/2, box['y']+box['height']/2)
            await page.mouse.down()
        elif event == 'tap':
            await page.locator(selector).tap()
        else:
            await page.locator(selector).click(force=True)
    chooser = await pending.value
    assert await chooser.element.get_attribute('id') == input_id
    assert await chooser.element.get_attribute('accept') is None
    if event == 'hold':
        await page.mouse.up()
    await chooser.set_files(payload)
    if payload:
        await page.wait_for_function('([kind,count])=>completedImports[kind]===count+1', arg=[kind, completed])


async def wait_loaded(page, input_id, name):
    await page.wait_for_function('''([id,name])=>document.getElementById(id+'Display')?.textContent===name''', arg=[input_id, name])
    assert await page.locator('#'+input_id).input_value() == ''
    assert await page.locator('#'+input_id).evaluate('e=>e.files.length') == 0


async def select_with_mime(page, input_id, payload):
    # Playwright substitutes a guessed MIME for mimeType="". Use a real browser
    # File here so the empty-MIME regression actually reaches the empty gate.
    actual = await page.evaluate('''({id,name,type,base64})=>{
      const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
      const file=new File([bytes],name,{type}), dataTransfer=new DataTransfer();
      dataTransfer.items.add(file);
      const input=document.getElementById(id);input.files=dataTransfer.files;
      input.dispatchEvent(new Event('change',{bubbles:true}));return file.type;
    }''', {'id': input_id, 'name': payload['name'], 'type': payload['mimeType'], 'base64': base64.b64encode(payload['buffer']).decode()})
    assert actual == payload['mimeType']


async def reject(page, input_id, payload, drop=None):
    before = await snapshot(page)
    await page.evaluate('window.importStatuses=[]')
    if drop:
        await drop_file(page, drop, payload)
    else:
        await select_with_mime(page, input_id, payload)
    await page.wait_for_function('importStatuses.some(s=>s.error)')
    await page.wait_for_timeout(100)
    statuses = await page.evaluate('importStatuses')
    assert all(s['error'] for s in statuses), statuses
    assert before == await snapshot(page), (payload['name'], before, await snapshot(page))
    assert await page.locator('#'+input_id).input_value() == ''


async def drop_file(page, selector, payload):
    await page.evaluate('''({selector,name,type,base64})=>{
      const bytes=Uint8Array.from(atob(base64),c=>c.charCodeAt(0));
      const dataTransfer=new DataTransfer();dataTransfer.items.add(new File([bytes],name,{type}));
      document.querySelector(selector).dispatchEvent(new DragEvent('drop',{bubbles:true,cancelable:true,dataTransfer}));
    }''', {'selector': selector, 'name': payload['name'], 'type': payload['mimeType'], 'base64': base64.b64encode(payload['buffer']).decode()})


async def main():
    subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y', '-i', str(OUT/'synthetic.wav'), '-codec:a', 'libmp3lame', '-b:a', '64k', str(OUT/'picker.MP3')], check=True)
    (OUT/'picker.LRC').write_text(LRC)
    mp3 = (OUT/'picker.MP3').read_bytes()
    result = {'cases': {}, 'page_errors': [], 'limits': 'Chromium Linux; chooser cancel is simulated. No physical iPad/Safari or native Files filter test.'}
    async with async_playwright() as p:
        browser = await p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH', '/usr/bin/chromium'), args=['--no-sandbox'])
        page = await browser.new_page(viewport={'width': 1024, 'height': 768}, has_touch=True, is_mobile=True)
        page.on('pageerror', lambda e: result['page_errors'].append(str(e)))
        await page.goto(BASE)
        await page.wait_for_function('window.player')
        await page.evaluate('''()=>{
          player.state.autoPlay=false;player.getBackground().setStaticMode(true);
          window.importStatuses=[];
          const show=player.showStatus.bind(player);
          player.showStatus=(text,error=false)=>{importStatuses.push({text,error});show(text,error)};
          window.importCalls={audio:0,captions:0};window.completedImports={audio:0,captions:0};
          for(const [key,method] of [['audio','loadMusicFromFile'],['captions','loadLyricFromFile']]){
            const original=player[method].bind(player);
            player[method]=async file=>{importCalls[key]++;await original(file);completedImports[key]++};
          }
        }''')
        # Initial play and empty-caption hint share the unrestricted inputs.
        await page.evaluate('player.controlPanel.style.display="none"')
        await choose(page, '#playPauseBtn', 'musicFile', str(OUT/'picker.MP3'))
        await wait_loaded(page, 'musicFile', 'picker.MP3')
        await choose(page, '#lyricAreaHint', 'lyricFile', str(OUT/'picker.LRC'), 'tap')
        await wait_loaded(page, 'lyricFile', 'picker.LRC')
        result['cases']['initial_play_and_caption_hint'] = True

        # Every visible/legacy button uses the same unrestricted chooser.
        for selector, kind, input_id, name, payload in [
            ('#openPracticeAudio', 'audio', 'musicFile', 'toolbar.Mp3', mp3),
            ('#openPracticeLyrics', 'captions', 'lyricFile', 'toolbar.LrC', LRC.encode()),
            ('#musicFileBtn', 'audio', 'musicFile', 'panel.MP3', mp3),
            ('#lyricFileBtn', 'captions', 'lyricFile', 'panel.LRC', LRC.encode()),
        ]:
            if 'FileBtn' in selector:
                await page.evaluate('player.controlPanel.style.display="";player.controlPanel.style.width="320px";player.controlPanel.style.right="20px";player.controlPanel.style.opacity="1"')
            await choose(page, selector, input_id, {'name': name, 'mimeType': 'application/octet-stream', 'buffer': payload}, 'tap' if 'Practice' in selector else 'click')
            await wait_loaded(page, input_id, name)
            result['cases'][selector] = True
        await page.evaluate('player.controlPanel.style.display="none"')
        for selector, input_id, filename in [('#playPauseBtn', 'musicFile', 'picker.MP3'), ('#fullscreenBtn', 'lyricFile', 'picker.LRC')]:
            for event in ['contextmenu', 'hold']:
                await choose(page, selector, input_id, str(OUT/filename), event)
                await wait_loaded(page, input_id, filename)
                result['cases'][selector+'_'+event] = True

        # True same-path reselection, not two distinct in-memory File objects.
        for kind, input_id, filename, selector in [('audio', 'musicFile', 'picker.MP3', '#openPracticeAudio'), ('captions', 'lyricFile', 'picker.LRC', '#openPracticeLyrics')]:
            for _ in range(2):
                count = await page.evaluate('completedImports.'+kind)
                await choose(page, selector, input_id, str(OUT/filename))
                await page.wait_for_function('([kind,count])=>completedImports[kind]===count+1', arg=[kind, count])
                await wait_loaded(page, input_id, filename)
            before = await snapshot(page)
            calls = await page.evaluate('importCalls')
            # Playwright cannot drive the OS Cancel button; exercise both event shapes.
            await choose(page, selector, input_id, [])
            await page.locator('#'+input_id).dispatch_event('cancel')
            await page.locator('#'+input_id).dispatch_event('change')
            assert before == await snapshot(page)
            assert calls == await page.evaluate('importCalls')
            count = await page.evaluate('completedImports.'+kind)
            await choose(page, selector, input_id, str(OUT/filename))
            await page.wait_for_function('([kind,count])=>completedImports[kind]===count+1', arg=[kind, count])
            result['cases'][kind+'_same_path_twice_cancel_reopen'] = True

        for i, mime in enumerate(['', 'application/octet-stream', 'image/png', 'text/plain']):
            for input_id, extension, data in [('musicFile', 'MP3', mp3), ('lyricFile', 'LRC', LRC.encode())]:
                name = f'mime-{i}.{extension}'
                await select_with_mime(page, input_id, {'name': name, 'mimeType': mime, 'buffer': data})
                await wait_loaded(page, input_id, name)
            await page.wait_for_function('player.getAudio().duration>59')
            assert (await snapshot(page))['lines'] == ['First', 'Second', 'Third']
            result['cases']['mime_'+(mime or 'empty')] = True
        await page.locator('#lyricFile').set_input_files({'name': 'caption#1.SRT', 'mimeType': 'application/octet-stream', 'buffer': srt(3).encode()})
        await wait_loaded(page, 'lyricFile', 'caption#1.SRT')
        assert len((await snapshot(page))['lines']) == 3
        result['cases']['uppercase_srt_with_hash'] = True
        await select_with_mime(page, 'lyricFile', {'name': 'export', 'mimeType': '', 'buffer': LRC.encode()})
        await wait_loaded(page, 'lyricFile', 'export')
        assert (await snapshot(page))['lines'] == ['First', 'Second', 'Third']
        result['cases']['empty_mime_content_detection'] = True
        ttml = b'<tt xmlns="http://www.w3.org/ns/ttml"><body><div><p begin="00:00:00.000" end="00:00:03.000">TTML sentence</p></div></body></tt>'
        await page.locator('#lyricFile').set_input_files({'name': 'export.TTML', 'mimeType': 'application/octet-stream', 'buffer': ttml})
        await wait_loaded(page, 'lyricFile', 'export.TTML')
        assert (await snapshot(page))['lines'] == ['TTML sentence']
        result['cases']['uppercase_ttml_dispatch'] = True

        for input_id, cases in [
            ('musicFile', [('note.txt', '', b'not audio'), ('empty.MP3', '', b''), ('fake.MP3', 'audio/mpeg', b'not mp3'), ('picture.png', 'image/png', b'bad')]),
            ('lyricFile', [('arbitrary.bin', '', b'not timed captions'), ('empty.LRC', '', b''), ('untimed.txt', 'text/plain', b'plain prose'), ('metadata.LRC', '', b'[ar:Someone]'), ('blank.LRC', '', b'[00:00.00]'), ('binary.LRC', '', b'\x00\x01[00:00.00]bad'), ('bad.TTML', 'text/plain', b'<tt><body>broken'), ('picture.png', 'image/png', b'bad')]),
        ]:
            for name, mime, data in cases:
                await reject(page, input_id, {'name': name, 'mimeType': mime, 'buffer': data})
                result['cases']['reject_'+input_id+'_'+name] = True

        # Dropping an oddly typed MP3 must not misroute it to cover art.
        for selector, input_id, name, data in [('#albumCoverLarge', 'musicFile', 'drop.MP3', mp3), ('#lyricsPanel', 'lyricFile', 'drop.LRC', LRC.encode())]:
            await drop_file(page, selector, {'name': name, 'mimeType': 'image/png', 'buffer': data})
            await wait_loaded(page, input_id, name)
            await reject(page, input_id, {'name': 'bad.'+name.split('.')[-1], 'mimeType': '', 'buffer': b'invalid'}, drop=selector)
            result['cases']['drop_'+input_id] = True

        # The panel reload works even though both native FileLists are empty.
        await page.evaluate('player.controlPanel.style.display="";player.controlPanel.style.width="320px";player.controlPanel.style.right="20px";player.controlPanel.style.opacity="1"')
        counts = await page.evaluate('completedImports')
        await page.locator('#loadFiles').click(force=True)
        await page.wait_for_function('c=>completedImports.audio===c.audio+1 && completedImports.captions===c.captions+1', arg=counts)
        assert (await snapshot(page))['audio'] == 'drop.MP3'
        assert (await snapshot(page))['captions'] == 'drop.LRC'
        result['cases']['panel_reload_retained_files'] = True

        # A slow earlier read cannot overwrite a newer choice or revive reset.
        await page.evaluate('''async()=>{
          const slow=new File(['x'],'slow.lrc');let release;
          slow.text=()=>new Promise(resolve=>release=resolve);
          const pending=player.loadLyricFromFile(slow);
          await player.loadLyricFromFile(new File(['[00:00.00]Newest'],'newest.LRC'));
          release('[00:00.00]Stale');await pending;
        }''')
        assert (await snapshot(page))['lines'] == ['Newest']
        result['cases']['latest_caption_read_wins'] = True
        await page.evaluate('''async data=>{
          const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
          await Promise.all([
            player.loadMusicFromFile(new File([bytes],'earlier.MP3')),
            player.loadMusicFromFile(new File([bytes],'latest.MP3')),
          ]);
        }''', base64.b64encode(mp3).decode())
        assert (await snapshot(page))['audio'] == 'latest.MP3'
        await page.wait_for_function('player.state.songTitle==="latest"')
        result['cases']['latest_audio_selection_wins'] = True
        # Direct and URL paths also must not turn parse failures into success.
        for text in ['not timed', 'data:text/plain;base64,bm90IHRpbWVk']:
            before = await snapshot(page)
            await page.evaluate('importStatuses=[]')
            assert await page.evaluate('text=>player.processLyricInput(text)', text) is False
            statuses = await page.evaluate('importStatuses')
            assert statuses and all(s['error'] for s in statuses), statuses
            assert before == await snapshot(page)
        await page.route('**/invalid-captions.LRC', lambda route: route.fulfill(status=200, body='not timed'))
        await page.evaluate('importStatuses=[];player.musicUrl.value="";player.lyricUrl.value=location.origin+"/invalid-captions.LRC"')
        await page.evaluate('player.loadFromURLs()')
        assert all(s['error'] for s in await page.evaluate('importStatuses'))
        result['cases']['direct_base64_url_parse_errors'] = True
        await page.evaluate('''async data=>{
          const bytes=Uint8Array.from(atob(data),c=>c.charCodeAt(0));
          const pending=player.loadMusicFromFile(new File([bytes],'pending.MP3'));
          player.resetPlayer();await pending;await player.loadFromFiles();
        }''', base64.b64encode(mp3).decode())
        assert not (await snapshot(page)).get('audio')
        result['cases']['reset_during_audio_validation'] = True
        await page.evaluate('''async()=>{
          const slow=new File(['x'],'slow.lrc');let release;
          slow.text=()=>new Promise(resolve=>release=resolve);
          const pending=player.loadLyricFromFile(slow);player.resetPlayer();
          release('[00:00.00]Stale');await pending;await player.loadFromFiles();
        }''')
        st = await snapshot(page)
        assert not st.get('audio') and not st.get('captions') and st['lines'] == [] and st['music'] == '', st
        result['cases']['reset_clears_retained_and_pending_files'] = True
        await browser.close()
    assert not result['page_errors'], result['page_errors']
    (OUT/'file-import-results.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    asyncio.run(main())
