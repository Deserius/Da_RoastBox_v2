import { useEffect, useMemo, useRef, useState } from "react";
import { mediaObjectUrl } from "@/lib/media";
import { useShowPlayer } from "@/hooks/useShowPlayer";
import { useShowDraft } from "@/hooks/useShowDraft";
import { crowd } from "@/lib/crowdEngine";

const POINTS = { none: 0, small: 1, medium: 2, big: 4, explosive: 6 };
const STAMPS = {
  ooh: "😮 OOOOOH!", groan: "😬 THE CROWD GROANS", cheer: "🙌 CROWD GOES WILD!",
  explosive: "🔥 STANDING OVATION!", big: "😂 BIG LAUGH!", medium: "😆 LAUGHS!", small: "😏 chuckles",
};
const SPLASH_MS = 2600;
const LINEUP_STEP_MS = 550;
const HOTSEAT_MS = 2200;

// Reveal just this beat, word by word, in time with its own voice (or the silent fallback).
const TypingText = ({ text = "", beatIndex, getSpeech }) => {
  const [n, setN] = useState(0);
  const words = useMemo(() => text.trim().split(/\s+/).filter(Boolean), [text]);
  const textRef = useRef(null);
  useEffect(() => {
    let raf;
    setN(0);
    const tick = () => {
      const speech = getSpeech();
      if (!speech || speech.index !== beatIndex || speech.startedAt === null) {
        raf = requestAnimationFrame(tick);
        return;
      }
      const audio = speech.audio;
      const progress = speech.finished ? 1 : audio && Number.isFinite(audio.duration) && audio.duration > 0
        ? audio.currentTime / audio.duration
        : (performance.now() - speech.startedAt) / speech.durationMs;
      const fraction = Math.max(0, Math.min(1, progress));
      setN(Math.min(words.length, Math.ceil(words.length * fraction)));
      if (fraction < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [beatIndex, getSpeech, words]);
  useEffect(() => {
    const bubble = textRef.current?.closest(".th-bubble");
    if (bubble) bubble.scrollTop = bubble.scrollHeight;
  }, [n]);
  return (
    <span ref={textRef} data-testid="theater-typing-text" aria-hidden="true">
      {words.slice(0, n).join(" ")}
      {n < words.length && <span className="caret">▍</span>}
    </span>
  );
};

const Sparks = () => (
  <div className="th-sparks" aria-hidden="true">
    {Array.from({ length: 14 }, (_, i) => <i key={i} style={{ "--i": i }} />)}
  </div>
);

const Splash = () => (
  <div className="th-splash" data-testid="theater-splash">
    <div className="th-splash-ring" aria-hidden="true" />
    <div className="th-intro-eyebrow"><span>LIVE</span> THE MIC IS HOT</div>
    <div className="th-welcome">WELCOME TO</div>
    <div className="th-logo">DA ROASTBOX!</div>
    <div className="th-splash-tagline">THE CROWD IS READY. THE HEAT IS ON.</div>
    <div className="th-flames" aria-hidden="true">🔥 🔥 🔥</div>
  </div>
);

const Lineup = ({ lineup, title }) => (
  <div className="th-lineup" data-testid="theater-lineup">
    <div className="th-intro-eyebrow">MAKE SOME NOISE FOR</div>
    <div className="th-title">{title}</div>
    <div className="th-lineup-row">
      {lineup.map((p, i) => (
        <div key={p.id} className="th-comic" style={{ animationDelay: `${i * LINEUP_STEP_MS}ms`, "--c": "#ff783e" }} data-testid={`theater-comic-${p.id}`}>
          <div className="th-comic-portrait">
            <img src={`/${p.image}`} alt={p.name} />
            <span className="th-comic-number" aria-hidden="true">{String(i + 1).padStart(2, "0")}</span>
          </div>
          <div className="th-comic-name">{p.displayName || p.name}</div>
          <div className="th-comic-role">{p.role}</div>
        </div>
      ))}
    </div>
    <div className="th-lineup-caption">ONE STAGE. NO MERCY.</div>
  </div>
);

const HotSeat = ({ photo, name, battle }) => (
  <div className="th-hotseat" data-testid="theater-hotseat">
    <div className="th-intro-eyebrow">ALL EYES ON YOU</div>
    <div className="th-title">{battle ? "ROAST BATTLE" : "IN THE HOT SEAT"}</div>
    <div className="th-hotseat-frame">
      {photo ? <img src={photo} alt="" className="th-hotseat-photo" /> : <div className="th-hotseat-placeholder" aria-hidden="true">🎤</div>}
      <span className="th-hotseat-badge">{battle ? "MAIN EVENT" : "TONIGHT'S GUEST"}</span>
    </div>
    <div className="th-hotseat-name">{name || (battle ? "Winner takes the crowd" : "Our brave guest")}</div>
    <div className="th-hotseat-caption">{battle ? "LET THE BATTLE BEGIN" : "TURN UP THE HEAT"}</div>
  </div>
);

// One comic at a time, full frame, while their walk-on line plays.
const PersonaCard = ({ persona, media, index, total, text, beatIndex, getSpeech }) => (
  <div className="th-open th-open-persona" key={persona.id} data-testid={`theater-open-persona-${persona.id}`}>
    <div className="th-open-eyebrow"><span>0{index + 1}</span> OF {String(total).padStart(2, "0")} · IN THE LINEUP</div>
    <div className="th-open-frame">
      {media && <img className="th-open-portrait" src={media} alt={persona.displayName || persona.name} data-testid="theater-open-portrait" />}
      <span className="th-open-badge">{persona.role || "ROASTER"}</span>
    </div>
    <div className="th-open-name">{persona.displayName || persona.name}</div>
    <p className="th-open-roast" data-testid="theater-lineup-roast" aria-label={text}>
      <TypingText text={text} beatIndex={beatIndex} getSpeech={getSpeech} />
    </p>
  </div>
);

const GuestCard = ({ photo, name, battle }) => (
  <div className="th-open th-open-guest" data-testid="theater-open-guest">
    <div className="th-open-eyebrow">ALL EYES ON YOU</div>
    <div className="th-open-frame">
      {photo ? <img className="th-open-portrait" src={photo} alt="" data-testid="theater-open-guest-photo" />
             : <div className="th-open-placeholder" aria-hidden="true">🎤</div>}
      <span className="th-open-badge">{battle ? "MAIN EVENT" : "TONIGHT'S GUEST"}</span>
    </div>
    <div className="th-open-title">{battle ? "IN THE HOT SEAT" : "IN THE HOT SEAT"}</div>
    <div className="th-open-name">{name || (battle ? "Winner takes the crowd" : "Our brave guest")}</div>
  </div>
);

const HostCard = ({ text, stage }) => (
  <div className="th-open th-open-host" data-testid={`theater-open-${stage}`}>
    <div className="th-open-eyebrow"><span>LIVE</span> THE MIC IS HOT</div>
    <div className="th-open-welcome">WELCOME TO</div>
    <div className="th-open-logo">DA ROASTBOX!</div>
    <div className="th-open-flames" aria-hidden="true">🔥 🔥 🔥</div>
    <p className="th-open-caption">{text}</p>
  </div>
);

export const RoastTheater = ({ transcript, personaById, images = [], lineupIds, subjectName, battle, mode = "roast", battleStyle = "classic", onClose, onBeatDone, onFinish }) => {
  const [phase, setPhase] = useState("splash");
  const [stamp, setStamp] = useState(null);
  const [live, setLive] = useState({});
  const [photos, setPhotos] = useState([]);
  const [mediaError, setMediaError] = useState("");
  const [beatVolume, setBeatVolume] = useShowDraft("shared.beatVolume", 0.7);
  const safeBeatVolume = Number.isFinite(Number(beatVolume)) ? Math.max(0, Math.min(1, Number(beatVolume))) : 0.7;
  const [crowdVolume, setCrowdVolume] = useShowDraft("shared.crowdVolume", 1);
  const safeCrowdVolume = Number.isFinite(Number(crowdVolume)) ? Math.max(0, Math.min(1, Number(crowdVolume))) : 1;
  const rootRef = useRef(null);
  const lineup = useMemo(() => [...new Set(lineupIds?.length ? lineupIds : transcript.map((b) => b.persona_id))]
    .map((id) => personaById[id]).filter(Boolean), [lineupIds, transcript, personaById]);
  const imageKey = images.join("\n");
  const stagedOpen = useMemo(() => transcript.some((b) => b.stage), [transcript]);
  useEffect(() => {
    let active = true;
    const abort = new AbortController();
    const urls = new Set();
    const paths = imageKey ? imageKey.split("\n") : [];
    Promise.all(paths.map(async (path) => {
      if (!path.startsWith("/api/")) return path;
      try {
        const url = await mediaObjectUrl(path, abort.signal);
        if (!active) { URL.revokeObjectURL(url); return ""; }
        urls.add(url);
        return url;
      } catch {
        if (active) setMediaError("Some media couldn't be loaded. Check your connection or reopen the show.");
        return "";
      }
    })).then((loaded) => { if (active) setPhotos(loaded); });
    return () => { active = false; abort.abort(); urls.forEach((url) => URL.revokeObjectURL(url)); };
  }, [imageKey]);

  useEffect(() => { crowd.setVolume(safeCrowdVolume); }, [safeCrowdVolume]);
  useEffect(() => { crowd.setBeatVolume(safeBeatVolume); }, [safeBeatVolume]);

  const { play, stop, activeIdx, currentSpeech, needsAudioTap, resumeAudio, useCaptionsOnly } = useShowPlayer({
    onMediaError: () => setMediaError("Some media couldn't be loaded. Check your connection or reopen the show."),
    onBeatDone: (beat, i) => {
      setLive((s) => ({ ...s, [beat.persona_id]: (s[beat.persona_id] || 0) + (POINTS[beat.laugh_after] || 0) }));
      onBeatDone?.(beat, i);
    },
    onReaction: (beat, i) => {
      const key = ["ooh", "groan", "cheer"].includes(beat.reaction) ? beat.reaction : beat.laugh_after;
      if (STAMPS[key] && key !== "none") setStamp({ text: STAMPS[key], id: i });
    },
    onFinish: () => { setPhase("outro"); onFinish?.(); },
  });

  useEffect(() => {
    let mounted = true;
    const timers = [];
    const lineupMs = lineup.length * LINEUP_STEP_MS + 900;
    const at = (ms, fn) => timers.push(setTimeout(fn, ms));
    if (stagedOpen) {
      // The script carries its own opening beats, so the cards are driven by the
      // voice lines instead of fixed timers. Legacy roasts keep the old choreography.
      play(transcript, {
        introMs: 0,
        rapBattle: mode === "battle" && battleStyle === "rap",
      });
    } else {
      play(transcript, {
        introMs: SPLASH_MS + lineupMs + HOTSEAT_MS,
        rapBattle: mode === "battle" && battleStyle === "rap",
        onIntroStart: () => {
          if (!mounted) return;
          at(SPLASH_MS, () => { setPhase("lineup"); crowd.stageCue("lineup"); });
          at(SPLASH_MS + lineupMs, () => { setPhase("hotseat"); crowd.stageCue("hotseat"); });
        },
      });
    }
    return () => { mounted = false; timers.forEach(clearTimeout); stop(); };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { if (activeIdx >= 0) setPhase("show"); }, [activeIdx]);
  useEffect(() => {
    if (!stamp) return undefined;
    const id = setTimeout(() => setStamp(null), 1700);
    return () => clearTimeout(id);
  }, [stamp]);

  const close = () => { stop(); if (document.fullscreenElement) document.exitFullscreen?.(); onClose?.(); };
  const fullscreen = () => rootRef.current?.requestFullscreen?.().catch(() => {});

  const beat = activeIdx >= 0 ? transcript[activeIdx] : null;
  const p = beat ? personaById[beat.persona_id] || {} : {};
  const imageIndex = Math.max(0, Math.min(Number(beat?.image_index) || 0, photos.length - 1));
  const photo = photos[imageIndex] || photos[0];
  const winner = mode === "battle" && battle && personaById[battle.winner];

  return (
    <div className="theater" ref={rootRef} role="dialog" aria-modal="true" aria-label="Roast show" data-testid="roast-theater">
      <div className="th-spotlight" />
      <Sparks />
      {mediaError && <div role="alert" className="th-media-error">{mediaError}</div>}
      <div className="th-topbar">
        <span className="badge-live">LIVE</span>
        {mode === "battle" && lineup.length === 2 && (
          <div className="th-score" data-testid="theater-score">
            {lineup.map((x) => <span key={x.id} style={{ color: "#ffb07d" }}>{x.displayName} {live[x.id] || 0}</span>)}
          </div>
        )}
        <div className="th-controls">
          {beat && <span className="th-progress" data-testid="theater-progress">{activeIdx + 1}/{transcript.length}</span>}
          <details className="th-mix" data-testid="theater-mix-controls">
            <summary aria-label="Adjust crowd volume" title="Adjust crowd volume" data-testid="theater-mix-toggle">♪</summary>
            <div className="th-mix-panel">
              <label htmlFor="theater-crowd-volume">Crowd volume <output>{Math.round(safeCrowdVolume * 100)}%</output></label>
              <input id="theater-crowd-volume" type="range" min="0" max="1" step="0.05" value={safeCrowdVolume}
                onChange={(e) => setCrowdVolume(Number(e.target.value))} data-testid="theater-crowd-volume" />
              {mode === "battle" && battleStyle === "rap" && <>
                <label htmlFor="theater-beat-volume">Beat volume <output>{Math.round(safeBeatVolume * 100)}%</output></label>
                <input id="theater-beat-volume" type="range" min="0" max="1" step="0.05" value={safeBeatVolume}
                  onChange={(e) => setBeatVolume(Number(e.target.value))} data-testid="theater-beat-volume" />
              </>}
              <small>Voices stay out front.</small>
            </div>
          </details>
          <button className="btn-ghost" onClick={fullscreen} aria-label="Enter full screen" data-testid="theater-fullscreen-btn">⛶</button>
          <button className="btn-ghost" onClick={close} aria-label="Close roast show" data-testid="theater-close-btn">✕</button>
        </div>
      </div>

      {stagedOpen && beat?.stage === "open_persona" && (
        <PersonaCard persona={personaById[beat.introduced_persona_id || beat.persona_id] || { id: beat.introduced_persona_id || beat.persona_id }}
          media={beat.media || (personaById[beat.introduced_persona_id || beat.persona_id]?.image ? `/${personaById[beat.introduced_persona_id || beat.persona_id].image}` : null)}
          index={Number(beat.persona_index ?? 0)} total={lineup.length || 1}
          text={beat.text} beatIndex={activeIdx} getSpeech={currentSpeech} />
      )}
      {stagedOpen && beat?.stage === "open_guest" && (
        <GuestCard photo={photos[0]} name={subjectName} battle={mode === "battle"} />
      )}
      {stagedOpen && (beat?.stage === "open_host" || beat?.stage === "open_lineup") && (
        <HostCard text={beat.text} stage={beat.stage} />
      )}
      {stagedOpen && !beat?.stage && activeIdx < 0 && <Splash />}

      {!stagedOpen && phase === "splash" && <Splash />}
      {!stagedOpen && phase === "lineup" && <Lineup lineup={lineup} title={mode === "battle" ? "TONIGHT'S FIGHTERS" : "TONIGHT'S ROASTERS"} />}
      {!stagedOpen && phase === "hotseat" && <HotSeat photo={photos[0]} name={subjectName} battle={mode === "battle"} />}

      {(!stagedOpen || (beat && !beat.stage)) && phase === "show" && beat && (
        <div className="th-stage" data-testid="theater-stage">
          {photo ? (
            <>
              <img className="th-photo-backdrop" src={photo} alt="" aria-hidden="true" />
              <img className="th-photo" src={photo} alt="" data-testid="theater-photo" />
            </>
          ) : <div className="th-photo-empty" aria-hidden="true">🎤</div>}
          <div className="th-stage-shade" aria-hidden="true" />
          <div className="th-stage-brand" aria-hidden="true">DA ROASTBOX!</div>
          <div className="th-bubble-wrap" key={activeIdx} style={{ "--c": "#ff783e" }}>
            <div className="th-speaker">
              {p.image && <img className="th-avatar" src={`/${p.image}`} alt="" />}
              <div className="th-speaker-label">
                <span>ON THE MIC</span>
                <strong>{p.displayName || p.name || "Roaster"}</strong>
              </div>
            </div>
            <div className="th-bubble" data-testid="theater-bubble" role="group" aria-label={`${p.displayName || p.name || "Roaster"}: ${beat.text || ""}`}>
              <TypingText text={beat.text} beatIndex={activeIdx} getSpeech={currentSpeech} />
            </div>
          </div>
        </div>
      )}
      {stamp && <div className="th-stamp" key={stamp.id} data-testid="theater-stamp">{stamp.text}</div>}
      {needsAudioTap && <div className="th-audio-gate" role="alert" data-testid="theater-audio-gate">
        <div className="th-audio-card">
          <strong>Ready for the show?</strong>
          <p>Your browser needs a tap to play the roasters' voices.</p>
          <button type="button" className="btn-primary" onClick={resumeAudio} data-testid="theater-resume-audio">🔊 Tap to play sound</button>
          <button type="button" className="btn-ghost" onClick={useCaptionsOnly} data-testid="theater-captions-only">Continue with captions only</button>
        </div>
      </div>}

      {phase === "outro" && (
        <div className="th-outro" data-testid="theater-outro">
          <div className="th-intro-eyebrow">ONE MORE ROUND OF APPLAUSE</div>
          {winner ? (
            <>
              <div className="th-title">🏆 WINNER</div>
              <img src={`/${winner.image}`} alt={winner.name} className="th-winner-img" style={{ borderColor: "#ff783e" }} />
              <div className="th-outro-name" style={{ color: "#ffb07d" }}>{winner.displayName}</div>
            </>
          ) : (
            <>
              {photos[0] && <img src={photos[0]} alt="" className="th-hotseat-photo small" />}
              <div className="th-title">THE HOT SEAT SURVIVED</div>
              <div className="th-outro-name" data-testid="theater-thanks">Thank you, {subjectName || "our brave guest"}!</div>
            </>
          )}
          <div className="th-outro-audience">AND THANK YOU EVERYBODY FOR COMING</div>
          <div className="th-outro-motto" data-testid="theater-motto"><strong>DA ROASTBOX!</strong><br />Where people come to get roasted and leave <b>burnt crispy.</b></div>
          <div className="th-outro-actions">
            <button className="btn-primary" onClick={close} data-testid="theater-done-btn">That&apos;s a wrap</button>
          </div>
        </div>
      )}
    </div>
  );
};
