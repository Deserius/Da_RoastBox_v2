import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { SkipForward, Volume2, VolumeX } from "lucide-react";
import "@/styles/cinematic-intro.css";

const LOGO = "/assets/intro/hae-official-selection.png";
const SOUND = "/assets/intro/hae-cinematic-swoosh.mp3";
const DURATION = 6900;
const IMPACT = 1.7;

// Deterministic droplets keep the animation identical on every device, without
// a heavyweight 3D runtime or downloading a large video.
const droplets = Array.from({ length: 68 }, (_, i) => {
  const rand = (n) => { const v = Math.sin((i + 1) * (n + 7) * 73.13) * 19327.31; return v - Math.floor(v); };
  return { vx: (rand(1) - .5) * 2, vy: .42 + rand(2) * .85,
    size: 1.1 + rand(3) * 2.6, delay: rand(4) * .3, shade: rand(5) };
});

// Priming an AudioContext tells the browser this page really wants sound; some
// builds allow element playback once the context is running.
let sharedAudioContext = null;
function primeAudioContext() {
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    sharedAudioContext = sharedAudioContext || new Ctx();
    const ctx = sharedAudioContext;
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
    const buffer = ctx.createBuffer(1, 1, 22050);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    source.start(0);
  } catch { /* Priming is only a hint; ignore browsers that refuse it. */ }
}


function Water({ run, reduced }) {
  const ref = useRef(null);
  useLayoutEffect(() => {
    if (reduced) return undefined;
    const canvas = ref.current;
    const ctx = canvas?.getContext("2d");
    if (!ctx) return undefined;
    let frame, w, h, ratio;
    const started = performance.now();
    const resize = () => {
      const rect = canvas.getBoundingClientRect();
      w = rect.width; h = rect.height; ratio = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.round(w * ratio));
      canvas.height = Math.max(1, Math.round(h * ratio));
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
    };
    resize();
    window.addEventListener("resize", resize, { passive: true });
    const draw = (now) => {
      const elapsed = (now - started) / 1000 - IMPACT;
      ctx.clearRect(0, 0, w, h);
      if (elapsed >= 0 && elapsed < 4.7) {
        const x = w / 2, surface = h * .65;
        const unit = Math.min(w * .38, h * .34, 330);
        // Expanding, foreshortened rings make the floor read as liquid rather
        // than a flat decorative line. Every ring fades as energy dissipates.
        for (let i = 0; i < 6; i++) {
          const age = elapsed - i * .22;
          if (age < 0) continue;
          const opacity = Math.max(0, .48 * Math.exp(-age * 1.05));
          const radius = unit * (.12 + age * .82);
          ctx.beginPath();
          ctx.ellipse(x, surface + 2 + age * 5, radius, Math.max(2, radius * .12), 0, 0, Math.PI * 2);
          ctx.lineWidth = Math.max(.5, 2.2 - age * .65);
          ctx.strokeStyle = `rgba(226, 181, 108, ${opacity})`;
          ctx.stroke();
        }
        // An initial crown of water, followed by ballistic droplets.
        if (elapsed < .72) {
          const fade = Math.max(0, 1 - elapsed / .72);
          const spread = unit * (.22 + elapsed * .75);
          const rise = unit * Math.sin(Math.min(1, elapsed / .72) * Math.PI) * .36;
          const grad = ctx.createLinearGradient(x, surface - rise, x, surface + 10);
          grad.addColorStop(0, `rgba(255, 222, 164, ${fade * .65})`);
          grad.addColorStop(1, `rgba(114, 84, 56, ${fade * .04})`);
          ctx.fillStyle = grad;
          ctx.beginPath();
          ctx.moveTo(x - spread, surface);
          for (let j = 0; j <= 10; j++) {
            const px = x - spread + (2 * spread * j) / 10;
            const high = j % 2 ? rise * .43 : rise * (.72 + .2 * Math.sin(j));
            ctx.lineTo(px, surface - high);
          }
          ctx.lineTo(x + spread, surface + 3);
          ctx.closePath(); ctx.fill();
        }
        droplets.forEach((d) => {
          const age = elapsed - d.delay;
          if (age <= 0 || age > 2.1) return;
          const px = x + d.vx * unit * age * .9;
          const py = surface - d.vy * unit * age + unit * .73 * age * age;
          if (py > surface + 2 || px < 0 || px > w) return;
          const alpha = Math.min(.9, Math.max(0, (1 - age / 2.1) * (d.shade * .3 + .5)));
          ctx.beginPath(); ctx.ellipse(px, py, d.size * .7, d.size * (1 + age * .55), d.vx * -.25, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255, ${Math.round(220 + d.shade * 25)}, ${Math.round(168 + d.shade * 65)}, ${alpha})`;
          ctx.fill();
        });
      }
      frame = requestAnimationFrame(draw);
    };
    frame = requestAnimationFrame(draw);
    return () => { cancelAnimationFrame(frame); window.removeEventListener("resize", resize); };
  }, [run, reduced]);
  return <canvas ref={ref} className="hae-water-fx" aria-hidden="true" />;
}

export default function CinematicIntro({ onDone }) {
  const [run, setRun] = useState(0);
  const [soundOn, setSoundOn] = useState(false);
  const [reduced] = useState(() => window.matchMedia?.("(prefers-reduced-motion: reduce)").matches || false);
  const audioRef = useRef(null);
  const doneRef = useRef(onDone);
  doneRef.current = onDone;

  useLayoutEffect(() => {
    if (run > 0 && audioRef.current && !audioRef.current.paused) {
      // The gesture unlocks playback; align its playhead once the restarted
      // visual scene actually commits, even on a slow device.
      try { audioRef.current.currentTime = 0; } catch { /* Media may still be loading. */ }
    }
  }, [run]);

  useEffect(() => {
    const audio = audioRef.current;
    let active = true;
    const tryPlay = () => {
      if (active && audio) {
        const attempt = audio.play();
        if (attempt?.then) {
          attempt.then(() => { if (active) setSoundOn(true); }).catch(() => { if (active) setSoundOn(false); });
        }
      }
    };
    let removeUnlock = null;
    if (run === 0 && !reduced && audio) {
      // Ask for sound at once, keep asking on a short backoff (some browsers
      // only allow it once the page is interactive), and take the first gesture
      // as the unlock. Nothing here requires the visitor to press a sound button.
      primeAudioContext();
      tryPlay();
      const retries = [90, 260, 600, 1200].map((ms) => window.setTimeout(() => { if (audio.paused) tryPlay(); }, ms));
      const unlock = () => { primeAudioContext(); if (!audio.paused) return; tryPlay(); };
      window.addEventListener("pointerdown", unlock);
      window.addEventListener("keydown", unlock);
      window.addEventListener("touchstart", unlock);
      removeUnlock = () => {
        retries.forEach((id) => window.clearTimeout(id));
        window.removeEventListener("pointerdown", unlock);
        window.removeEventListener("keydown", unlock);
        window.removeEventListener("touchstart", unlock);
      };
    }
    const timer = window.setTimeout(() => doneRef.current(), reduced ? 1800 : DURATION);
    const onEscape = (event) => { if (event.key === "Escape") doneRef.current(); };
    window.addEventListener("keydown", onEscape);
    return () => {
      active = false;
      if (typeof removeUnlock === "function") removeUnlock();
      window.clearTimeout(timer);
      window.removeEventListener("keydown", onEscape);
    };
  }, [run, reduced]);
  useEffect(() => {
    const audio = audioRef.current;
    return () => { audio?.pause(); };
  }, []);

  const toggleSound = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (soundOn) { audio.pause(); setSoundOn(false); return; }
    // Restart the scene and sound in the same user gesture, rather than playing
    // a late impact sound out of sync with the picture.
    try { audio.currentTime = 0; } catch { /* Metadata may still be loading. */ }
    const attempt = audio.play();
    setRun((value) => value + 1);
    if (attempt?.then) attempt.then(() => setSoundOn(true)).catch(() => setSoundOn(false));
  };

  return (
    <section className={`hae-intro ${reduced ? "hae-intro-reduced" : ""}`} aria-label="Hustler Anomalies Enterprises introduction" data-testid="cinematic-intro">
      <audio ref={audioRef} src={SOUND} preload="auto" />
      <div key={run} className="hae-intro-scene" aria-hidden="true">
        <div className="hae-spotlight hae-spotlight-left" />
        <div className="hae-spotlight hae-spotlight-right" />
        <div className="hae-horizon" />
        <div className="hae-logo-fall"><img src={LOGO} alt="" /></div>
        <div className="hae-flash" />
        <div className="hae-liquid">
          <img src={LOGO} alt="" className="hae-reflection" />
          <div className="hae-water-shimmer" />
        </div>
        <Water run={run} reduced={reduced} />
        <div className="hae-caption"><span /> A HUSTLER ANOMALIES ENTERPRISES PRODUCTION <span /></div>
      </div>
      <div className="hae-controls">
        {!reduced && <button type="button" onClick={toggleSound} className="hae-control" data-testid="intro-sound-btn">
          {soundOn ? <Volume2 size={16} aria-hidden="true" /> : <VolumeX size={16} aria-hidden="true" />}
          {soundOn ? "Mute" : "Replay with sound"}
        </button>}
        <button type="button" onClick={() => doneRef.current()} className="hae-control hae-skip" data-testid="skip-intro-btn">
          Skip intro <SkipForward size={15} aria-hidden="true" />
        </button>
      </div>
      <span className="hae-sr-only">A gold company logo falls into dark water. The introduction can be skipped.</span>
    </section>
  );
}
