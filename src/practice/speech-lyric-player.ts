import { DomLyricPlayer, type LyricLine } from '@applemusic-like-lyrics/core';
import { TapGesture, DoubleTapGesture, DOUBLE_TAP_WINDOW_MS, dragSeekTime, dragSelectionIndex } from './timing';

type Line = DomLyricPlayer['currentLyricLineObjects'][number];
// Runtime fields of pinned alpha.5, omitted from its declarations by @internal.
type LineSprings = { lineTransforms: {
  posY: { setTargetPosition(position: number): void; setPosition(position: number): void; getCurrentPosition(): number };
  scale: { setTargetPosition(position: number): void };
} };
type LineLayout = [top: number, scale: number, opacity: number, blur: number];
type DragPointer = {
  id: number; y: number; time: number; velocity: number; line?: Line;
  startX: number; startY: number; startedAt: number; dragging: boolean;
  seek: boolean; inside: boolean; eligible: boolean; bounds: DOMRect;
};

/** Keep AMLL's renderer; replace alpha.5's competing touch/mouse scroll handlers. */
export class SpeechLyricPlayer extends DomLyricPlayer {
  // Present at runtime in pinned alpha.5; omitted from its .d.ts by @internal.
  declare readonly lyricLinesSize: WeakMap<Line, [number, number]>;
  declare readonly lyricLineElementMap: WeakMap<Element, Line>;
  private manual = false;
  private positionHeld = false;
  private manualAnchor = 0;
  private layoutAnchor = 0;
  private heldLayout: { line: Line; top: number } | null = null;
  private followTimer = 0;
  private inertia = 0;
  private layoutFrame = 0;
  private syncLayout = false;
  private snapLayout = false;
  private pointer: DragPointer | null = null;
  private dragSeekEnabled = true;
  private seekDuration = NaN;
  private lyricDelayMs = 0;
  private dragGuide = document.createElement('div');
  private dragLabel = document.createElement('div');
  private dragCandidate: { line: Line; seconds: number } | null = null;
  private previewLine: Line | null = null;
  private lineLayout = new WeakMap<Line, LineLayout>();
  private reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  private firstMainLine: Line | null = null;
  private lastMainLine: Line | null = null;
  private dragScrollBounds: [number, number] | null = null;
  private gesture = new TapGesture();
  private doubleTap = new DoubleTapGesture();
  private singleTapTimer = 0;
  private animated = new Set<Line>();
  private targetTop = new WeakMap<Line, number>();
  private events = new AbortController();

  constructor() {
    super();
    this.isPlaying = false;
    this.allowScroll = false; // Disable only the upstream input handlers.
    const el = this.getElement();
    el.classList.add('speech-lyrics');
    el.style.touchAction = 'none';
    el.setAttribute('aria-label', 'Speech transcript. Tap to play/pause; double-tap a sentence or drag to the centre guide and release to seek.');
    this.dragGuide.className = 'drag-seek-guide';
    this.dragGuide.hidden = true;
    this.dragLabel.className = 'drag-seek-label';
    this.dragLabel.setAttribute('role', 'status');
    this.dragLabel.setAttribute('aria-live', 'polite');
    this.dragGuide.appendChild(this.dragLabel);
    el.appendChild(this.dragGuide);
    const opts = { signal: this.events.signal };
    el.addEventListener('pointerdown', this.onPointerDown, opts);
    el.addEventListener('pointermove', this.onPointerMove, opts);
    el.addEventListener('pointerup', this.onPointerUp, opts);
    el.addEventListener('pointercancel', this.onPointerCancel, opts);
    el.addEventListener('lostpointercapture', this.onPointerCancel, opts);
    el.addEventListener('wheel', this.onWheel, { ...opts, passive: false });
    window.addEventListener('resize', () => this.cancelPointer(), opts);
    window.addEventListener('blur', () => this.cancelPointer(), opts);
    document.addEventListener('visibilitychange', () => { if (document.hidden) this.cancelPointer(); }, opts);
    document.addEventListener('pointerdown', e => {
      if (this.pointer && e.pointerType === 'touch' && e.pointerId !== this.pointer.id) this.cancelPointer();
      if (!(e.target instanceof Node) || !el.contains(e.target) || this.isControl(e.target)) this.cancelTap();
    }, { ...opts, capture: true });
    // Pointer activation is handled once on release; suppress compatibility clicks.
    el.addEventListener('click', (e) => {
      if (e.detail !== 0 && !this.isControl(e.target)) { e.preventDefault(); e.stopImmediatePropagation(); }
    }, { ...opts, capture: true });
    el.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      if (this.isControl(e.target)) return;
      this.cancelTap();
      const line = this.lineAt(e.target);
      if (line) { e.preventDefault(); e.stopPropagation(); this.activate(line); }
    }, opts);
  }

  get isFollowing() { return !this.manual; }
  get isPositionHeld() { return this.positionHeld; }
  get isDragSeekEnabled() { return this.dragSeekEnabled; }

  /** A committed sentence choice stays where it was until explicit Follow. */
  holdPosition(startTime: number) {
    cancelAnimationFrame(this.inertia);
    const wasManual = this.manual;
    // Freeze the displayed layout, even if playback has queued a newer anchor
    // or a position spring is still moving when the second tap arrives.
    const visibleLines = [...this.animated].filter(line => {
      const top = (line as Line & LineSprings).lineTransforms.posY.getCurrentPosition();
      return top < this.size[1] && top + (this.lyricLinesSize.get(line)?.[1] ?? 0) > 0;
    });
    const visible = visibleLines.find(line => line.getLine().startTime === startTime) ?? visibleLines[0];
    this.heldLayout = visible ? { line: visible,
      top: (visible as Line & LineSprings).lineTransforms.posY.getCurrentPosition() } : null;
    this.beginManual();
    if (!wasManual) this.manualAnchor = this.layoutAnchor;
    this.positionHeld = true;
  }

  setDragSeekEnabled(enabled: boolean) {
    this.cancelTap();
    if (this.pointer) this.cancelPointer();
    this.dragSeekEnabled = enabled;
    this.element.setAttribute('aria-label', enabled
      ? 'Speech transcript. Tap to play/pause; double-tap a sentence or drag to the centre guide and release to seek.'
      : 'Speech transcript. Tap to play/pause; drag to browse; double-tap a sentence to seek.');
  }

  setSeekContext(duration: number, delayMs: number) {
    if (Object.is(duration, this.seekDuration) && delayMs === this.lyricDelayMs) return;
    // A changed recording, delay or duration invalidates a gesture already in progress.
    this.cancelTap();
    if (this.pointer) this.cancelPointer();
    this.seekDuration = duration;
    this.lyricDelayMs = delayMs;
  }

  private hideDragPreview() {
    this.dragGuide.hidden = true;
    this.dragCandidate = null;
    this.setPreviewLine(null);
    delete this.dragGuide.dataset.startMs;
    delete this.dragGuide.dataset.audioSeconds;
  }

  private setPreviewLine(line: Line | null) {
    if (line === this.previewLine) return;
    const previous = this.previewLine;
    previous?.getElement().removeAttribute('data-drag-candidate');
    this.previewLine = line;
    line?.getElement().setAttribute('data-drag-candidate', 'true');
    // Reapply only the visual parameters through AMLL's existing renderer.
    // Do not enable a lyric, change its word clock, or seek audio during preview.
    for (const target of [previous, line]) {
      const layout = target && this.lineLayout.get(target);
      if (target && layout) target.setTransform(...layout);
    }
  }

  private updateDragPreview() {
    const p = this.pointer;
    if (!p?.dragging || !p.seek) return;
    this.dragGuide.hidden = false;
    const rows: { line: Line; top: number; height: number }[] = [];
    // AMLL's cached unscaled boxes stay stable while the preview spring grows.
    // No DOM measurements per move; detached/re-entering rows need visual order,
    // not the insertion order of the animated set.
    for (const line of this.animated) {
      if (line.getLine().isBG || !line.getLine().words.some(word => word.word.trim())) continue;
      const top = this.targetTop.get(line);
      const height = this.lyricLinesSize.get(line)?.[1];
      if (top === undefined || !height) continue;
      rows.push({ line, top, height });
    }
    rows.sort((a, b) => a.top - b.top);
    const nearest = rows[dragSelectionIndex(rows, this.size[1] / 2)]?.line;
    const seconds = nearest ? dragSeekTime(nearest.getLine().startTime, this.lyricDelayMs, this.seekDuration) : null;
    this.dragCandidate = p.inside && nearest && seconds !== null ? { line: nearest, seconds } : null;
    this.setPreviewLine(this.dragCandidate?.line ?? null);
    const candidate = this.dragCandidate;
    let label = '';
    if (candidate) {
      const ms = Math.round(candidate.seconds * 1000);
      const time = `${String(Math.floor(ms / 60000)).padStart(2, '0')}:${String(Math.floor(ms / 1000) % 60).padStart(2, '0')}.${String(ms % 1000).padStart(3, '0')}`;
      label = time;
      this.dragGuide.dataset.startMs = String(candidate.line.getLine().startTime);
      this.dragGuide.dataset.audioSeconds = String(candidate.seconds);
    } else {
      delete this.dragGuide.dataset.startMs;
      delete this.dragGuide.dataset.audioSeconds;
    }
    this.dragLabel.hidden = !candidate;
    if (this.dragLabel.textContent !== label) this.dragLabel.textContent = label;
  }

  private isControl(target: EventTarget | null): boolean {
    let el = target instanceof Element ? target : null;
    while (el && el !== this.element) {
      // Transcript rows themselves have role=button for keyboard seeking.
      if (this.lyricLineElementMap.has(el)) return false;
      if (el.matches('a, button, input, select, textarea, form, label, summary, [role="button"], [role="slider"], [role="switch"], [role="checkbox"], [role="textbox"], [contenteditable]:not([contenteditable="false"])')) return true;
      el = el.parentElement;
    }
    return false;
  }

  private cancelTap() {
    clearTimeout(this.singleTapTimer);
    this.singleTapTimer = 0;
    this.doubleTap.reset();
  }

  private lineAt(target: EventTarget | null): Line | undefined {
    let el = target instanceof Element ? target : null;
    while (el && el !== this.element) {
      const line = this.lyricLineElementMap.get(el);
      if (line) return line as Line;
      el = el.parentElement;
    }
  }

  private activate(line: Line) {
    this.dispatchEvent(new CustomEvent('line-activate', { detail: line.getLine().startTime }));
  }

  private onPointerDown = (e: PointerEvent) => {
    if (!e.isPrimary) { this.cancelPointer(); return; }
    if (e.button !== 0 || this.isControl(e.target)) { this.cancelTap(); return; }
    // Hold the first tap while another pointer is down: a long press or drag
    // must not let its pending playback action fire partway through the gesture.
    clearTimeout(this.singleTapTimer);
    this.singleTapTimer = 0;
    cancelAnimationFrame(this.inertia);
    clearTimeout(this.followTimer);
    this.gesture.begin(e.clientX, e.clientY, e.timeStamp);
    // Geometry is read once at gesture start. A resize cancels rather than using stale bounds.
    const bounds = this.element.getBoundingClientRect();
    const inset = parseFloat(getComputedStyle(this.element).paddingTop) || 0;
    this.dragGuide.style.top = `${inset + this.size[1] / 2}px`;
    this.pointer = { id: e.pointerId, y: e.clientY, time: e.timeStamp, velocity: 0, line: this.lineAt(e.target),
      startX: e.clientX, startY: e.clientY, startedAt: e.timeStamp, dragging: false,
      seek: this.dragSeekEnabled, inside: true, eligible: true, bounds };
    this.element.setPointerCapture(e.pointerId);
  };

  private onPointerMove = (e: PointerEvent) => {
    const p = this.pointer;
    if (!p || p.id !== e.pointerId) return;
    this.gesture.move(e.clientX, e.clientY);
    if (this.gesture.moved) this.cancelTap();
    p.inside = e.clientX >= p.bounds.left && e.clientX <= p.bounds.right &&
      e.clientY >= p.bounds.top && e.clientY <= p.bounds.bottom;
    if (!p.dragging) {
      if (e.timeStamp - p.startedAt > 450) p.eligible = false;
      const dx = Math.abs(e.clientX - p.startX), dy = Math.abs(e.clientY - p.startY);
      if (dy <= 10 || dy <= dx) return;
      // A long hold may still scroll, but must never arm a release-to-seek.
      // Restrict the seek action, not scrolling itself (including slow drags).
      if (!p.eligible) p.seek = false;
      p.dragging = true;
    }
    this.cancelTap();
    this.beginManual();
    const dy = p.y - e.clientY;
    p.velocity = dy / Math.max(1, e.timeStamp - p.time);
    this.scrollByPixels(dy);
    p.y = e.clientY; p.time = e.timeStamp;
  };

  private onPointerUp = (e: PointerEvent) => {
    const p = this.pointer;
    if (!p || p.id !== e.pointerId) return;
    this.gesture.move(e.clientX, e.clientY);
    p.inside = e.clientX >= p.bounds.left && e.clientX <= p.bounds.right &&
      e.clientY >= p.bounds.top && e.clientY <= p.bounds.bottom;
    if (p.dragging && e.clientY !== p.y) this.onPointerMove(e);
    // Flush only the final pending layout so release uses the last finger position.
    if (p.dragging && p.seek) {
      if (this.layoutFrame) { cancelAnimationFrame(this.layoutFrame); this.renderLayout(); }
      this.updateDragPreview();
    }
    const selected = p.dragging && p.seek && p.inside ? this.dragCandidate?.line : undefined;
    this.pointer = null; // Clear before capture release or seek can dispatch more events.
    if (this.element.hasPointerCapture(e.pointerId)) this.element.releasePointerCapture(e.pointerId);
    this.hideDragPreview();
    if (selected) {
      this.cancelTap();
      // Commit even when this is the current sentence: replay its start once.
      this.activate(selected); // Never run inertia or a pending single tap here.
    } else if (this.gesture.isTap(e.timeStamp) && p.inside) {
      if (this.doubleTap.accept(p.line ?? this.element, e.clientX, e.clientY, e.timeStamp)) {
        this.cancelTap();
        if (p.line) this.activate(p.line);
      } else {
        this.singleTapTimer = window.setTimeout(() => {
          this.cancelTap();
          this.dispatchEvent(new Event('playback-toggle'));
        }, DOUBLE_TAP_WINDOW_MS);
      }
    } else {
      this.cancelTap();
      if (p.dragging && !p.seek && e.timeStamp - p.time < 100) this.startInertia(p.velocity);
    }
    this.scheduleFollow();
  };

  private onPointerCancel = (e: PointerEvent) => {
    // Normal release also loses capture, after the single-tap timer is armed.
    if (this.pointer || e.type === 'pointercancel') this.cancelPointer();
  };
  private cancelPointer() {
    this.cancelTap();
    const p = this.pointer;
    this.pointer = null;
    this.hideDragPreview();
    if (p && this.element.hasPointerCapture(p.id)) this.element.releasePointerCapture(p.id);
    cancelAnimationFrame(this.inertia);
    this.scheduleFollow();
  }

  private onWheel = (e: WheelEvent) => {
    if (e.ctrlKey) return; // Do not swallow browser zoom.
    e.preventDefault();
    if (this.pointer) this.cancelPointer();
    cancelAnimationFrame(this.inertia);
    this.beginManual();
    this.scrollByPixels(e.deltaY * (e.deltaMode === 1 ? 24 : e.deltaMode === 2 ? this.size[1] : 1));
    this.scheduleFollow();
  };

  private beginManual() {
    this.cancelTap();
    clearTimeout(this.followTimer);
    if (this.manual) return;
    this.manual = true;
    this.manualAnchor = this.scrollToIndex;
    this.element.classList.add('manual-scroll');
    this.dispatchEvent(new Event('follow-change'));
  }

  private scrollByPixels(delta: number) {
    const bounds = this.pointer?.seek && this.pointer.dragging && this.dragScrollBounds
      ? this.dragScrollBounds : this.scrollBoundary;
    this.scrollOffset = Math.max(bounds[0], Math.min(bounds[1], this.scrollOffset + delta));
    void this.calcLayout(true);
  }

  private startInertia(velocity: number) {
    velocity = Math.max(-3, Math.min(3, velocity));
    let last = performance.now();
    const step = (now: number) => {
      const dt = Math.min(32, now - last); last = now;
      const before = this.scrollOffset;
      this.scrollByPixels(velocity * dt);
      velocity *= Math.exp(-dt / 180); // Time-based friction, consistent on 60/120 Hz screens.
      if (Math.abs(velocity) > 0.02 && before !== this.scrollOffset) this.inertia = requestAnimationFrame(step);
      else this.scheduleFollow();
    };
    this.inertia = requestAnimationFrame(step);
  }

  private scheduleFollow() {
    clearTimeout(this.followTimer);
    if (this.manual && !this.positionHeld) this.followTimer = window.setTimeout(() => this.resetScroll(), 5000);
  }

  override resetScroll() {
    if (this.pointer) this.cancelPointer();
    this.hideDragPreview();
    this.cancelTap();
    cancelAnimationFrame(this.inertia);
    clearTimeout(this.followTimer);
    this.positionHeld = false;
    this.heldLayout = null;
    this.manual = false;
    this.element.classList.remove('manual-scroll');
    super.resetScroll();
    void this.calcLayout();
    this.dispatchEvent(new Event('follow-change'));
  }

  protected override getCurrentInterlude() {
    return this.manual ? undefined : super.getCurrentInterlude();
  }

  override setCurrentTime(time: number, isSeek = false) {
    super.setCurrentTime(Math.round(time), isSeek);
    for (const index of this.hotLines) {
      const line = this.currentLyricLineObjects[index];
      // Core can retain a hot index while replacing the DOM row on import.
      // Also reset same-row word animations when seeking within its interval.
      if (isSeek) void line?.enable(time);
      line?.setMaskAnimationState(time);
      if (!this.isPlaying) void line?.pause();
    }
    if (isSeek) {
      // alpha.5 selects its old buffered index before replacing the buffer on seek.
      const next = this.processedLines.findIndex(line => line.startTime >= time);
      this.scrollToIndex = this.hotLines.size ? Math.min(...this.hotLines)
        : next >= 0 ? next : Math.max(0, this.processedLines.length - 1);
      // A discontinuous clock must not mix old visible springs with newly
      // mounted rows already placed at the destination. Batch one atomic layout.
      this.snapLayout = true;
      void this.calcLayout(true);
    }
  }

  private renderLayout() {
    this.layoutFrame = 0;
    const currentAnchor = this.scrollToIndex;
    if (this.manual) this.scrollToIndex = this.manualAnchor;
    this.layoutAnchor = this.scrollToIndex;
    void super.calcLayout(this.syncLayout);
    if (this.heldLayout) {
      // Account for a queued spring or interlude spacer disappearing on seek.
      // Both layouts complete before paint; retain the selected row's position.
      const correction = (this.targetTop.get(this.heldLayout.line) ?? this.heldLayout.top) - this.heldLayout.top;
      this.heldLayout = null;
      if (Math.abs(correction) > 0.01) {
        this.scrollOffset += correction;
        void super.calcLayout(true);
      }
    }
    this.scrollToIndex = currentAnchor;
    this.syncLayout = false;
    this.snapLayout = false;
    // Unlike browsing, scrubbing must be able to centre both the first and last sentence.
    if (this.firstMainLine && this.lastMainLine) {
      const offsetFor = (line: Line) => (this.targetTop.get(line) ?? 0) + this.scrollOffset +
        (this.lyricLinesSize.get(line)?.[1] ?? this.size[1] / 5) / 2 - this.size[1] / 2;
      const min = offsetFor(this.firstMainLine);
      this.dragScrollBounds = [min, Math.max(min, offsetFor(this.lastMainLine))];
    } else this.dragScrollBounds = null;
    this.updateDragPreview();
  }

  override async calcLayout(sync = false) {
    this.syncLayout ||= sync;
    // ResizeObserver measures newly mounted wrapped rows after a seek. Their
    // corrected heights belong to the same snapped layout, not a new animation.
    this.snapLayout ||= sync;
    if (this.layoutFrame) return;
    this.layoutFrame = requestAnimationFrame(() => this.renderLayout());
  }

  override setLyricLines(lines: LyricLine[], initialTime = 0) {
    this.resetScroll();
    this.animated.clear();
    this.lineLayout = new WeakMap();
    this.firstMainLine = null; this.lastMainLine = null; this.dragScrollBounds = null;
    super.setLyricLines(lines, initialTime);
    for (const line of this.currentLyricLineObjects) {
      if (!line.getLine().isBG && line.getLine().words.some(word => word.word.trim())) {
        this.firstMainLine ??= line;
        this.lastMainLine = line;
      }
      const el = line.getElement();
      el.setAttribute('role', 'button'); el.tabIndex = 0;
      el.setAttribute('aria-label', `Seek to ${line.getLine().words.map(w => w.word).join('')}`);
      const transform = line.setTransform.bind(line);
      const resetSprings = (top: number, scale: number) => {
        // alpha.5 setPosition() leaves queuePosition alive. Clear its delayed
        // target through the spring API before the forced transform resets velocity.
        const springs = (line as Line & LineSprings).lineTransforms;
        springs.posY.setTargetPosition(top);
        springs.scale.setTargetPosition(scale);
      };
      let parked = false;
      line.setTransform = (top = 0, scale = 100, opacity = 1, blur = 0, force = false, delay = 0) => {
        this.lineLayout.set(line, [top, scale, opacity, blur]);
        const height = this.lyricLinesSize.get(line)?.[1] ?? this.size[1] / 5;
        const near = top < this.size[1] + height && top + height > -height;
        this.targetTop.set(line, top);
        if (line === this.previewLine) {
          // Keep the original measured box for selection/ordering. AMLL scales
          // about the row's vertical centre; cap growth for very tall wrapped text.
          if (!this.reducedMotion.matches) scale = 100 + Math.min(3, 1200 / Math.max(1, height));
          opacity = 1;
          blur = 0;
        }
        if (!near && (this.snapLayout || parked || !line.isInSight)) {
          if (!parked) { resetSprings(top, scale); transform(top, scale, opacity, 0, true, 0); line.hide(); }
          parked = true;
          this.animated.delete(line);
          return; // No style writes or springs for distant detached lines.
        }
        // Rows retired by update() also need a reset when they re-enter.
        const snap = force || parked || !this.animated.has(line) || this.manual || this.snapLayout;
        const smoothScale = this.manual && this.getEnableSpring() && !this.reducedMotion.matches
          && !force && !parked && this.animated.has(line);
        if (smoothScale) {
          // Drag position follows the finger immediately, while the same native
          // scale spring eases target emphasis. No additional CSS transform/loop.
          const posY = (line as Line & LineSprings).lineTransforms.posY;
          posY.setTargetPosition(top);
          posY.setPosition(top);
        } else if (snap) resetSprings(top, scale);
        transform(top, scale, opacity, this.manual ? 0 : Math.min(4, blur), snap && !smoothScale, snap ? 0 : delay);
        parked = false;
        this.animated.add(line);
        if (near) line.show();
      };
    }
    // Core's base import visits the old row objects before DOM creates new ones.
    this.hotLines.clear();
    this.bufferedLines.clear();
    this.setCurrentTime(initialTime, true);
  }

  override update(delta = 0) {
    if (!this.initialLayoutFinished || !this.isPageVisible) return;
    this.interludeDots.update(delta / 1000);
    this.bottomLine.update(delta / 1000);
    if (!this.supportMaskImage) this.element.style.setProperty('--amll-player-time', String(this.currentTime));
    for (const line of this.animated) {
      line.update(Math.min(50, delta) / 1000);
      const top = this.targetTop.get(line) ?? 0;
      const height = this.lyricLinesSize.get(line)?.[1] ?? 0;
      if (!line.isInSight && (top > this.size[1] + height || top + height < -height)) this.animated.delete(line);
    }
  }

  override dispose() {
    this.cancelTap();
    if (this.pointer) this.cancelPointer();
    this.events.abort();
    cancelAnimationFrame(this.layoutFrame);
    cancelAnimationFrame(this.inertia);
    clearTimeout(this.followTimer);
    super.dispose();
  }
}
