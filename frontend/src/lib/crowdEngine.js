// Comedy-club crowd engine (Web Audio): room tone bed, layered randomized reactions, ducking under speech.
const SFX_BASE = "/assets/sfx/crowd";
const BANK = {
  room: ["room_tone"],
  rapBeat: ["rap_beat"],
  intro: ["intro_cheer"],
  outro: ["applause_outro"],
  small: ["chuckle_1", "chuckle_2"],
  medium: ["laugh_med_1", "laugh_med_2"],
  big: ["laugh_big_1", "laugh_big_2"],
  explosive: ["explosive_1", "explosive_2"],
  ooh: ["ooh_1", "ooh_2"],
  groan: ["groan_1"],
};

// gain: main layer volume; layer: secondary bank mixed in for crowd depth; hold: ms the comic waits before next line.
const LEVELS = {
  none: { gain: 0, hold: 0 },
  small: { gain: 0.48, hold: 800, land: [130, 230] },
  medium: { gain: 0.68, layer: ["small", 0.22, 310], hold: 1500, land: [150, 260] },
  big: { gain: 0.82, layer: ["medium", 0.3, 400], hold: 2350, land: [170, 290] },
  explosive: { gain: 0.94, layer: ["big", 0.38, 340], hold: 3650, land: [190, 310] },
};

const rand = (a, b) => a + Math.random() * (b - a);
const pick = (arr) => arr[Math.floor(Math.random() * arr.length)];

// Slightly lower the whole crowd, then put every reaction (including delayed
// layers) well below the separate persona audio while a line is being spoken.
const CROWD_MASTER = 0.45;
const SPEECH_DUCK = 0.08;
const DUCK_ATTACK_S = 0.06;
const DUCK_RELEASE_S = 0.24;

class CrowdEngine {
  ctx = null;
  master = null;
  speechBus = null;
  musicBus = null;
  musicDuck = null;
  beat = null;
  beatStart = 0;
  beatVolume = 0.7;
  buffers = {};
  active = new Set();
  room = null;
  loading = null;
  volume = 1;
  lastSample = {};

  setVolume(value) {
    const next = Number(value);
    this.volume = Number.isFinite(next) ? Math.max(0, Math.min(1, next)) : 1;
    if (!this.ctx || !this.master) return;
    const gain = this.master.gain;
    const now = this.ctx.currentTime;
    if (typeof gain.cancelAndHoldAtTime === "function") gain.cancelAndHoldAtTime(now);
    else { gain.cancelScheduledValues(now); gain.setValueAtTime(gain.value, now); }
    gain.linearRampToValueAtTime(CROWD_MASTER * this.volume, now + 0.08);
  }

  unlock() {
    if (!this.ctx) {
      const Ctx = window.AudioContext || window.webkitAudioContext;
      if (!Ctx) return;
      this.ctx = new Ctx();
      const comp = this.ctx.createDynamicsCompressor();
      comp.threshold.value = -14;
      comp.ratio.value = 3;
      this.master = this.ctx.createGain();
      this.master.gain.value = CROWD_MASTER * this.volume;
      this.speechBus = this.ctx.createGain();
      this.speechBus.gain.value = 1;
      this.speechBus.connect(this.master).connect(comp).connect(this.ctx.destination);
      this.musicBus = this.ctx.createGain();
      this.musicBus.gain.value = 0.28 * this.beatVolume;
      this.musicDuck = this.ctx.createGain();
      this.musicDuck.gain.value = 1;
      this.musicBus.connect(this.musicDuck).connect(comp);
    }
    if (this.ctx.state === "suspended") this.ctx.resume();
    if (!this.loading) this.loading = this.preload();
    return this.loading;
  }

  async preload() {
    const names = [...new Set(Object.values(BANK).flat())];
    await Promise.all(names.map(async (n) => {
      try {
        const res = await fetch(`${SFX_BASE}/${n}.mp3`);
        this.buffers[n] = await this.ctx.decodeAudioData(await res.arrayBuffer());
      } catch { /* missing sfx is non-fatal */ }
    }));
  }

  play(bank, { gain = 1, delay = 0, loop = false, fadeIn = 0.05, bus = null } = {}) {
    const available = (BANK[bank] || []).filter((name) => this.buffers[name]);
    const fresh = available.filter((name) => name !== this.lastSample[bank]);
    const name = pick(fresh.length ? fresh : available);
    const buf = this.buffers[name];
    if (buf && !loop) this.lastSample[bank] = name;
    if (!this.ctx || !buf || gain <= 0) return null;
    const src = this.ctx.createBufferSource();
    src.buffer = buf;
    src.loop = loop;
    src.playbackRate.value = loop ? 1 : rand(0.98, 1.02);
    const g = this.ctx.createGain();
    const pan = this.ctx.createStereoPanner ? this.ctx.createStereoPanner() : null;
    const t = this.ctx.currentTime + delay / 1000;
    g.gain.setValueAtTime(0.0001, t);
    g.gain.exponentialRampToValueAtTime(gain, t + fadeIn);
    if (pan) { pan.pan.value = loop ? 0 : rand(-0.25, 0.25); src.connect(g).connect(pan).connect(bus || this.speechBus); }
    else src.connect(g).connect(bus || this.speechBus);
    src.start(t, loop ? 0 : rand(0, 0.025));
    const node = { src, g };
    if (!loop) {
      this.active.add(node);
      src.onended = () => this.active.delete(node);
    }
    return node;
  }

  fade(node, to, seconds) {
    if (!node || !this.ctx) return;
    const now = this.ctx.currentTime;
    node.g.gain.cancelScheduledValues(now);
    node.g.gain.setValueAtTime(Math.max(0.0001, node.g.gain.value), now);
    node.g.gain.exponentialRampToValueAtTime(Math.max(0.0001, to), now + seconds);
  }

  startRoom() {
    if (this.room) return;
    this.room = this.play("room", { gain: 0.16, loop: true, fadeIn: 1.2 });
  }

  // This shared bus also controls reactions that were scheduled before speech
  // but have not started yet. Individual-node fades missed those delayed layers.
  rampSpeechBus(to, seconds) {
    if (!this.ctx || !this.speechBus) return;
    const gain = this.speechBus.gain;
    const now = this.ctx.currentTime;
    if (typeof gain.cancelAndHoldAtTime === "function") gain.cancelAndHoldAtTime(now);
    else {
      gain.cancelScheduledValues(now);
      gain.setValueAtTime(gain.value, now);
    }
    gain.linearRampToValueAtTime(to, now + seconds);
  }

  rampMusicDuck(to, seconds) {
    if (!this.ctx || !this.musicDuck) return;
    const gain = this.musicDuck.gain, now = this.ctx.currentTime;
    if (typeof gain.cancelAndHoldAtTime === "function") gain.cancelAndHoldAtTime(now);
    else { gain.cancelScheduledValues(now); gain.setValueAtTime(gain.value, now); }
    gain.linearRampToValueAtTime(to, now + seconds);
  }
  setBeatVolume(value) {
    const next = Number(value);
    this.beatVolume = Number.isFinite(next) ? Math.max(0, Math.min(1, next)) : 0.7;
    if (!this.ctx || !this.musicBus) return;
    const gain = this.musicBus.gain, now = this.ctx.currentTime;
    gain.cancelScheduledValues(now); gain.setValueAtTime(gain.value, now);
    gain.linearRampToValueAtTime(0.28 * this.beatVolume, now + 0.08);
  }
  startBeat() {
    if (!this.ctx || this.beat) return;
    this.beatStart = this.ctx.currentTime;
    this.beat = this.play("rapBeat", { gain: 1, loop: true, fadeIn: 0.3, bus: this.musicBus });
  }
  msToBeat() {
    if (!this.ctx || !this.beat) return 0;
    const period = 60 / 90;
    const elapsed = Math.max(0, this.ctx.currentTime - this.beatStart);
    const remainder = elapsed % period;
    return remainder < 0.03 ? 0 : (period - remainder) * 1000;
  }
  stopBeat() {
    if (!this.beat) return;
    const node = this.beat; this.beat = null;
    this.fade(node, 0.0001, 0.25);
    setTimeout(() => { try { node.src.stop(); } catch { /* already stopped */ } }, 350);
  }
  // Duck independently so vocals stay intelligible while the rhythm remains audible.
  duck() { this.rampSpeechBus(SPEECH_DUCK, DUCK_ATTACK_S); this.rampMusicDuck(0.32, DUCK_ATTACK_S); }
  releaseDuck() { this.rampSpeechBus(1, DUCK_RELEASE_S); this.rampMusicDuck(1, DUCK_RELEASE_S); }

  /** Fire a crowd reaction. Returns ms the performer should hold before the next line. */
  react(level = "none", reaction = "laugh", { nextIsTag = false, rapidFire = false } = {}) {
    const L = LEVELS[level] || LEVELS.small;
    if (!this.ctx || (L.gain <= 0 && reaction === "laugh")) return 0;
    const land = L.land ? rand(...L.land) : 120;
    let extra = 0;
    if (reaction === "ooh") {
      this.play("ooh", { gain: 0.85, delay: land });
      extra = 700;
    } else if (reaction === "groan") {
      this.play("groan", { gain: 0.7, delay: land });
      extra = 400;
    } else if (reaction === "cheer") {
      this.play("intro", { gain: 0.6, delay: land + 200 });
    }
    if (L.gain > 0) {
      this.play(level, { gain: L.gain, delay: land + extra });
      if (L.layer && Math.random() < 0.65) this.play(L.layer[0], { gain: L.layer[1], delay: land + extra + L.layer[2] + rand(-60, 60) });
    }
    const reactionOnly = L.gain <= 0 && reaction !== "laugh" ? 1000 : 0;
    const hold = land + extra + Math.max(reactionOnly, L.hold * rand(0.92, 1.08));
    if (rapidFire) return Math.min(900, hold * 0.45);
    return nextIsTag ? hold * 0.45 : hold;
  }

  // Short, locally synthesized stage stingers; no network or provider calls.
  stageCue(stage) {
    if (!this.ctx || !this.master) return;
    const notes = stage === "lineup" ? [330, 415, 523] : stage === "hotseat" ? [147, 220, 294] : [196, 294, 392];
    notes.forEach((frequency, i) => {
      const start = this.ctx.currentTime + i * 0.085;
      const osc = this.ctx.createOscillator();
      const g = this.ctx.createGain();
      osc.type = "triangle";
      osc.frequency.setValueAtTime(frequency, start);
      g.gain.setValueAtTime(0.0001, start);
      g.gain.exponentialRampToValueAtTime(0.075, start + 0.025);
      g.gain.exponentialRampToValueAtTime(0.0001, start + 0.38);
      osc.connect(g).connect(this.speechBus);
      const node = { src: osc, g };
      this.active.add(node);
      osc.onended = () => this.active.delete(node);
      osc.start(start);
      osc.stop(start + 0.4);
    });
  }

  intro() {
    this.startRoom();
    this.stageCue("opening");
    this.play("intro", { gain: 0.8, delay: 150 });
    return 1600;
  }

  outro() {
    this.stageCue("outro");
    this.play("outro", { gain: 0.8, delay: 500 });
    if (this.room) { this.fade(this.room, 0.0001, 9); const r = this.room; this.room = null; setTimeout(() => r.src.stop(), 9500); }
  }

  stopAll() {
    this.stopBeat();
    this.active.forEach((n) => { this.fade(n, 0.0001, 0.3); setTimeout(() => { try { n.src.stop(); } catch { /* already stopped */ } }, 400); });
    this.active.clear();
    this.lastSample = {};
    if (this.room) { this.fade(this.room, 0.0001, 0.5); const r = this.room; this.room = null; setTimeout(() => { try { r.src.stop(); } catch { /* already stopped */ } }, 600); }
    // Do not leave a new show or a replay stuck at the previous speech level.
    this.releaseDuck();
  }
}

export const crowd = new CrowdEngine();
