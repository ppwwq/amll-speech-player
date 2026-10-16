"""Actual IndexedDB image bytes, reload/restart and failure/race regression.
All media are synthetic; injected storage failures are not physical disk exhaustion.
"""
import asyncio,base64,hashlib,json,shutil,struct,zlib
from playwright.async_api import async_playwright
from browser import BASE,OUT,load

def png(rgb):
 def chunk(kind,data):return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
 return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',32,32,8,2,0,0,0))+chunk(b'IDAT',zlib.compress((b'\0'+bytes(rgb)*32)*32))+chunk(b'IEND',b'')
A=png((30,90,180));B=png((20,170,80))
RESULT={'cases':{},'page_errors':[],'non_read_requests':[]}
def record(name):RESULT['cases'][name]=True;print('PASS',name,flush=True)
async def ready(page):
 await page.wait_for_function('window.player');await page.evaluate('Promise.all([player.localRestoreReady,player.backgroundRestoreReady])')
 await page.evaluate('player.state.autoPlay=false;player.getBackground().setStaticMode(true)')
async def phase(page,value):
 await page.wait_for_function('v=>document.getElementById("localSavePanel").dataset.backgroundPhase===v',arg=value)
async def stored(page):
 return await page.evaluate('''async()=>{const v=await player.localStore.readBackground();if(!v)return null;return {name:v.name,size:v.blob?.size,blob:v.blob instanceof Blob,keys:Object.keys(v),hash:v.blob instanceof Blob?[...new Uint8Array(await crypto.subtle.digest('SHA-256',await v.blob.arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join(''):null}}''')
async def upload(page,name='A.PNG',data=A,mime=''):
 await page.locator('#coverFile').set_input_files({'name':name,'mimeType':mime,'buffer':data})
 await page.wait_for_function('name=>player.selectedCoverFile?.name===name&&document.getElementById("coverFileDisplay")?.textContent===name',arg=name)
async def action(page,id):
 await page.locator('#localSavePanel').evaluate('e=>e.open=true');await page.locator('#'+id).click()
async def observe(context):
 await context.add_init_script('window.playCalls=0;const play=HTMLMediaElement.prototype.play;HTMLMediaElement.prototype.play=function(){playCalls++;return play.call(this)}')
 context.on('page',lambda p:p.on('pageerror',lambda e:RESULT['page_errors'].append(str(e))))
 context.on('request',lambda r:RESULT['non_read_requests'].append(r.url) if r.method not in ['GET','HEAD'] else None)

async def main():
 profile=OUT/'synthetic-background-profile'
 if profile.exists():shutil.rmtree(profile)
 async with async_playwright() as p:
  options={'executable_path':'/usr/bin/chromium','headless':True,'args':['--no-sandbox'],'viewport':{'width':1024,'height':768},'has_touch':True,'is_mobile':True}
  ctx=await p.chromium.launch_persistent_context(str(profile),**options);await observe(ctx)
  page=await ctx.new_page();await load(page);await ready(page)
  await page.evaluate('player.seekAudio(12.345);player.applyLyricDelay(750)')
  await page.wait_for_function('player.localMemory.lastProgress==="12.345:750"')
  media=await page.evaluate('player.localMemory.backend.read() .then(s=>s.media.id)')
  await page.locator('#backgroundStyle').evaluate('e=>{e.value="cover";e.dispatchEvent(new Event("change",{bubbles:true}))}')
  await upload(page);await phase(page,'saved')
  first=await stored(page);assert first['blob'] and first['hash']==hashlib.sha256(A).hexdigest()
  assert 'url' not in first['keys'] and first['size']==len(A)
  assert await page.locator('#coverFile').input_value()==''
  url=await page.evaluate('player.state.coverUrl');assert url.startswith('blob:')
  await page.reload();await ready(page);await phase(page,'saved')
  assert await page.evaluate('player.selectedCoverFile.name')=='A.PNG'
  assert await page.evaluate('player.state.coverUrl')!=url
  await page.wait_for_function('document.getElementById("albumCoverLarge").complete&&document.getElementById("albumCoverLarge").naturalWidth===32&&document.getElementById("albumCoverLarge").src===player.state.coverUrl')
  displayed_hash=await page.evaluate('''async()=>[...new Uint8Array(await crypto.subtle.digest('SHA-256',await (await fetch(player.state.coverUrl)).arrayBuffer()))].map(x=>x.toString(16).padStart(2,'0')).join('')''')
  assert displayed_hash==hashlib.sha256(A).hexdigest()
  assert await page.evaluate('player.state.backgroundType')=='cover'
  assert await page.evaluate('player.getAudio().paused&&playCalls===0&&Math.abs(player.getAudio().currentTime-12.345)<.03&&player.state.lyricDelay===750')
  assert (await stored(page))==first
  assert await page.evaluate('player.localMemory.backend.read().then(s=>s.media.id)')==media
  record('binary_hash_and_new_object_url_on_reload_with_complete_paused_media')
  await ctx.close();ctx=await p.chromium.launch_persistent_context(str(profile),**options);await observe(ctx)
  page=await ctx.new_page();await page.goto(BASE);await ready(page);await phase(page,'saved')
  assert (await stored(page))==first and await page.evaluate('player.selectedCoverFile.name')=='A.PNG'
  assert await page.evaluate('player.getAudio().paused&&playCalls===0')
  record('real_browser_process_restart_restores_image')
  await upload(page,'B.png',B,'application/octet-stream');await phase(page,'saved')
  assert (await stored(page))['hash']==hashlib.sha256(B).hexdigest()
  await upload(page,'B.png',B,'');await phase(page,'saved')
  await page.locator('#coverFile').dispatch_event('cancel')
  assert (await stored(page))['hash']==hashlib.sha256(B).hexdigest()
  record('replace_reselect_empty_wrong_mime_and_cancel')
  prior=await stored(page)
  for data in [b'',b'not an image']:
   await page.locator('#coverFile').set_input_files({'name':'bad.png','mimeType':'image/png','buffer':data});await phase(page,'error')
   assert await stored(page)==prior and await page.evaluate('player.selectedCoverFile.name')=='B.png'
  await page.evaluate('''()=>{const input=document.getElementById('coverFile'),dt=new DataTransfer();dt.items.add(new File([new Uint8Array(20*1024*1024+1)],'oversize.png',{type:'image/png'}));input.files=dt.files;input.dispatchEvent(new Event('change',{bubbles:true}))}''');await phase(page,'error')
  assert await stored(page)==prior and '20 MiB' in await page.locator('#backgroundSaveStatus').text_content()
  record('invalid_empty_and_oversize_images_preserve_previous_image')
  await page.evaluate('''()=>{window.realPut=IDBObjectStore.prototype.put;IDBObjectStore.prototype.put=function(value,key){if(key==='background')throw new DOMException('quota','QuotaExceededError');return realPut.call(this,value,key)}}''')
  await upload(page,'quota.png',A);await phase(page,'error')
  assert await stored(page)==prior and '空間不足' in await page.locator('#backgroundSaveStatus').text_content()
  await page.evaluate('()=>{IDBObjectStore.prototype.put=realPut}')
  await action(page,'saveLocalBackground');await phase(page,'saved')
  assert (await stored(page))['name']=='quota.png'
  record('quota_failure_keeps_old_record_and_retry_saves_current_preview')
  prior=await stored(page)
  await page.evaluate('''()=>{IDBObjectStore.prototype.put=function(v,k){const r=realPut.call(this,v,k);if(k==='background')r.addEventListener('success',()=>this.transaction.abort());return r}}''')
  await upload(page,'aborted.png',B);await phase(page,'error');assert await stored(page)==prior
  await page.evaluate('()=>{IDBObjectStore.prototype.put=realPut}')
  record('request_success_then_transaction_abort_does_not_report_saved')
  await page.evaluate('''()=>{window.realDelete=IDBObjectStore.prototype.delete;IDBObjectStore.prototype.delete=function(k){if(k==='background')throw new Error('blocked delete');return realDelete.call(this,k)}}''')
  await action(page,'clearLocalBackground');await phase(page,'error');assert await stored(page)==prior
  await page.evaluate('()=>{IDBObjectStore.prototype.delete=realDelete}')
  await action(page,'clearLocalBackground');await phase(page,'cleared')
  assert await stored(page) is None and await page.evaluate('player.state.coverUrl')==''
  assert await page.evaluate('player.localMemory.backend.read().then(s=>s.media.id)')==media
  await page.reload();await ready(page);await phase(page,'empty')
  assert await page.evaluate('player.selectedMusicFile!==null&&player.currentCaptions!==null')
  record('clear_image_retry_and_reload_preserve_audio_captions')
  await page.evaluate('''()=>{window.realWrite=player.localStore.writeBackground.bind(player.localStore);const gate=new Promise(r=>window.releaseWrite=r);player.localStore.writeBackground=async v=>{window.writeStarted=true;await gate;return realWrite(v)}}''')
  await upload(page,'pending.png',A);await page.wait_for_function('window.writeStarted')
  await action(page,'clearLocalBackground');await page.evaluate('releaseWrite()');await phase(page,'cleared')
  assert await stored(page) is None
  await page.evaluate('()=>{player.localStore.writeBackground=realWrite}')
  record('clear_wins_pending_write_without_resurrection')
  # The existing multi-file Load action can await audio before reloading a cover.
  # Its old snapshot must not replace a newer image or undo an intervening clear.
  for clear in [False,True]:
   await upload(page);await phase(page,'saved')
   await page.evaluate('''()=>{window.realLoadMusic=player.loadMusicFromFile.bind(player);const gate=new Promise(r=>window.releaseReload=r);player.loadMusicFromFile=async()=>{window.reloadStarted=true;await gate;return true};window.reloadingFiles=player.loadFromFiles()}''')
   await page.wait_for_function('window.reloadStarted')
   if clear:await action(page,'clearLocalBackground');await phase(page,'cleared')
   else:await upload(page,'changed-during-load.png',B);await phase(page,'saved')
   await page.evaluate('releaseReload()');await page.evaluate('window.reloadingFiles')
   await page.evaluate('()=>{player.loadMusicFromFile=realLoadMusic;window.reloadStarted=false}')
   if clear:assert await stored(page) is None and await page.evaluate('player.selectedCoverFile') is None
   else:assert (await stored(page))['name']=='changed-during-load.png' and await page.evaluate('player.selectedCoverFile.name')=='changed-during-load.png'
   record('multi_file_load_respects_'+('clear' if clear else 'newer_image'))
  await upload(page);await phase(page,'saved')
  await page.evaluate('''async()=>{const saved=await player.localStore.readBackground();window.realRead=player.localStore.readBackground.bind(player.localStore);const gate=new Promise(r=>window.releaseRead=r);player.localStore.readBackground=async()=>{await gate;return saved};player.backgroundRestoreReady=player.restoreLocalBackground()}''')
  await upload(page,'newest.png',B);await phase(page,'saved');await page.evaluate('releaseRead()');await page.evaluate('player.backgroundRestoreReady')
  assert await page.evaluate('player.selectedCoverFile.name')=='newest.png'
  await page.evaluate('()=>{player.localStore.readBackground=realRead}')
  record('manual_selection_wins_slow_restore')
  await page.evaluate('''async()=>{const db=await player.localStore.open();await new Promise((ok,no)=>{const tx=db.transaction('media','readwrite');tx.objectStore('media').put({version:1,url:'blob:expired'},'background');tx.oncomplete=ok;tx.onabort=no})}''')
  await page.reload();await ready(page);await phase(page,'error')
  assert await page.evaluate('!player.selectedCoverFile&&player.selectedMusicFile!==null&&player.getAudio().paused')
  await upload(page);await phase(page,'saved');record('old_missing_or_corrupt_url_record_does_not_break_media_and_can_recover')
  # Explicit URL input is visit-only and never replaces the saved local image.
  data_url='data:image/png;base64,'+base64.b64encode(B).decode()
  await page.evaluate('(s)=>player.processCoverInput(s)',data_url)
  assert (await stored(page))['hash']==hashlib.sha256(A).hexdigest()
  await page.reload();await ready(page);assert await page.evaluate('player.selectedCoverFile.name')=='A.PNG'
  record('temporary_url_does_not_overwrite_local_image')
  # The existing stats panel can be closed with its existing saved preference.
  await page.locator('#showFPS').evaluate('e=>{e.checked=true;e.dispatchEvent(new Event("change",{bubbles:true}))}')
  info=await page.evaluate('''()=>{player.stats.showPanel(1);const s=player.stats.dom.style;return {top:s.top,left:s.left,display:s.display,visible:player.stats.dom.children[1].style.display}}''')
  assert info=={'top':'0px','left':'0px','display':'block','visible':'block'},info
  await page.locator('#showFPS').evaluate('e=>{e.checked=false;e.dispatchEvent(new Event("change",{bubbles:true}))}')
  await page.reload();await ready(page);assert await page.evaluate('!player.state.showFPS&&player.stats.dom.style.display==="none"')
  record('existing_stats_checkbox_hides_panel_and_preference_survives_reload')
  before_cover=await page.evaluate('player.state.coverUrl')
  before_id=await page.evaluate('player.localMemory.savedId')
  await page.evaluate('''bytes=>{window.realTagsRead=window.jsmediatags.read;window.jsmediatags.read=(file,options)=>options.onSuccess({tags:{title:'Synthetic embedded artwork',picture:{data:bytes,format:'image/png'}}})}''',list(B))
  await page.locator('#musicFile').set_input_files(str(OUT/'synthetic.wav'))
  await page.wait_for_function('id=>player.localMemory.savedId&&player.localMemory.savedId!==id',arg=before_id)
  assert await page.evaluate('player.state.coverUrl')==before_cover
  assert (await stored(page))['hash']==hashlib.sha256(A).hexdigest()
  await page.evaluate('()=>{window.jsmediatags.read=realTagsRead}')
  record('replacing_audio_and_embedded_artwork_do_not_override_custom_image')
  for name,w,h in [('tablet',1024,768),('phone',390,844),('landscape-phone',844,390)]:
   await page.set_viewport_size({'width':w,'height':h});await action(page,'saveLocalBackground');await phase(page,'saved')
   r=await page.locator('#localSavePanel .save-details').bounding_box()
   assert r['x']>=0 and r['x']+r['width']<=w+1 and r['y']+r['height']<=h+1,r
   await page.screenshot(path=str(OUT/f'background-{name}.png'))
  record('existing_glass_menu_mobile_bounds')
  await action(page,'clearLocalSession');await phase(page,'cleared');await page.wait_for_function('document.getElementById("localSavePanel").dataset.phase==="cleared"')
  assert await stored(page) is None and await page.evaluate('player.localMemory.backend.read()') is None
  await page.reload();await ready(page);assert await page.evaluate('!player.selectedCoverFile&&!player.selectedMusicFile')
  record('clear_all_removes_both_independent_records')
  await upload(page);await phase(page,'saved')
  await page.evaluate('player.resetPlayer()');await phase(page,'cleared')
  assert await stored(page) is None and await page.evaluate('!player.selectedCoverFile&&player.state.coverUrl===""')
  await page.reload();await ready(page);assert await page.evaluate('!player.selectedCoverFile')
  record('full_reset_clears_image_without_restore_race')
  await ctx.close()
  ctx=await p.chromium.launch_persistent_context(str(OUT/'synthetic-background-blocked'),**options);await observe(ctx)
  await ctx.add_init_script('Object.defineProperty(window,"indexedDB",{get(){throw new DOMException("blocked","SecurityError")}})')
  page=await ctx.new_page();await page.goto(BASE);await ready(page)
  await upload(page);await phase(page,'error')
  assert await page.evaluate('player.state.coverUrl.startsWith("blob:")&&player.selectedCoverFile.name==="A.PNG"')
  await action(page,'clearLocalBackground');await phase(page,'error')
  record('blocked_storage_keeps_image_preview_and_clear_controls_usable')
  await ctx.close()
 assert not RESULT['page_errors'] and not RESULT['non_read_requests'],RESULT
 RESULT['limits']='Synthetic images/audio, local production build and persistent Chromium profiles. Storage failures injected; no physical iPad Safari or actual disk-exhaustion test.'
 (OUT/'local-background-results.json').write_text(json.dumps(RESULT,indent=2)+'\n')
 print(json.dumps(RESULT,indent=2))

if __name__=='__main__':asyncio.run(main())
