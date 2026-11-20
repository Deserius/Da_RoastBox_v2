import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";
import { crowd } from "@/lib/crowdEngine";
import { ShowTranscript } from "@/components/ShowTranscript";
import { PersonaBrowser } from "@/components/PersonaBrowser";
import { RoastTheater } from "@/components/theater/RoastTheater";
import { ComedyStyles } from "@/components/studio/ComedyStyles";
import { HeatControls, canUseInferno } from "@/components/studio/HeatControls";
import { useShowDraft } from "@/hooks/useShowDraft";
import { ShareButton } from "@/components/ShareButton";
import { ReelButton } from "@/components/ReelButton";
import ApiLoadError from "@/components/ApiLoadError";
import { imageError } from "@/lib/uploads";

const POINTS = { none: 0, small: 1, medium: 2, big: 4, explosive: 6 };

const Scoreboard = ({ a, b, live, result }) => {
  const scores = result?.scores || live;
  const total = Math.max(1, (scores[a?.id] || 0) + (scores[b?.id] || 0));
  return (
    <div className="scoreboard" data-testid="battle-scoreboard">
      {[a, b].map((p, i) => p && (
        <div key={p.id} className={`fighter ${result?.winner === p.id ? "winner" : ""}`} data-testid={`fighter-${i ? "b" : "a"}`}>
          <img src={`/${p.image}`} alt={p.name} style={{ borderColor: "#ff783e" }} />
          <div className="fighter-name" style={{ color: "#ffb07d" }}>{p.displayName}</div>
          <div className="fighter-score" data-testid={`fighter-score-${i ? "b" : "a"}`}>{scores[p.id] || 0}</div>
          <div className="meter"><span style={{ width: `${((scores[p.id] || 0) / total) * 100}%`, background: "#ff783e" }} /></div>
          {result?.winner === p.id && <div className="winner-badge" data-testid="battle-winner">🏆 WINNER</div>}
        </div>
      ))}
      <div className="vs">VS</div>
    </div>
  );
};

export default function BattlePage() {
  const { user, refresh } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [access, setAccess] = useState(null);
  const [personas, setPersonas] = useState([]);
  const [loadError, setLoadError] = useState(false);
  const [reload, setReload] = useState(0);
  const [picks, setPicks] = useShowDraft("battle.picks", []);
  const [battleStyle, setBattleStyle] = useShowDraft("battle.style", "classic");
  const [rounds, setRounds] = useShowDraft("battle.rounds", 3);
  const [subjectName, setSubjectName] = useShowDraft("battle.subjectName", "");
  const [context, setContext] = useShowDraft("battle.context", "");
  const [offLimits, setOffLimits] = useShowDraft("battle.offLimits", "");
  const [file, setFile] = useShowDraft("battle.file", null, { memoryOnly: true });
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(null);
  const [live, setLive] = useState({});
  const [revealed, setRevealed] = useState(false);
  const ringRef = useRef(null);

  const [heat, setHeat] = useShowDraft("shared.heat", canUseInferno(user) ? "inferno" : "fire");
  const [adult, setAdult] = useShowDraft("shared.adult", true);
  const [comedyStyles, setComedyStyles] = useShowDraft("shared.comedyStyles", []);
  const [theater, setTheater] = useState(false);
  const onBeatDone = (beat) => setLive((s) => ({ ...s, [beat.persona_id]: (s[beat.persona_id] || 0) + (POINTS[beat.laugh_after] || 0) }));
  const openTheater = () => { setLive({}); setRevealed(false); setTheater(true); };

  useEffect(() => {
    if (heat === "inferno" && user && !canUseInferno(user)) setHeat("fire");
  }, [heat, user, setHeat]);

  useEffect(() => {
    let active = true;
    setLoadError(false);
    Promise.all([api.get("/battle/access"), api.get("/personas")])
      .then(([battle, lineup]) => {
        if (active) { setAccess(battle.data); setPersonas(lineup.data.personas || []); }
      })
      .catch(() => { if (active) { setAccess(null); setLoadError(true); } });
    return () => { active = false; };
  }, [user?.roast_battle_unlocked, user?.lifetime_founder, user?.premium_personas_unlocked, user?.plan_tier, reload]);

  const byId = useMemo(() => Object.fromEntries(personas.map((p) => [p.id, p])), [personas]);
  const [a, b] = [byId[picks[0]], byId[picks[1]]];
  const premiumUsed = [a, b].some((p) => p?.is_premium);
  const cost = access ? access.base_cost + (premiumUsed ? access.premium_persona_cost : 0) : 0;

  const toggle = (p) => {
    if (p.locked) { toast("Premium roaster — unlock the bundle first", "error"); navigate("/credits"); return; }
    setPicks((cur) => (cur.includes(p.id) ? cur.filter((x) => x !== p.id) : cur.length >= 2 ? [cur[0], p.id] : [...cur, p.id]));
  };

  const fight = async () => {
    crowd.unlock();
    setTheater(false);
    setBusy(true); setShow(null); setLive({}); setRevealed(false);
    ringRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    const fd = new FormData();
    fd.append("persona_a", picks[0]);
    fd.append("persona_b", picks[1]);
    fd.append("rounds", rounds);
    fd.append("battle_style", battleStyle);
    if (subjectName) fd.append("subject_name", subjectName);
    if (context) fd.append("user_context", context);
    if (offLimits) fd.append("off_limits", offLimits);
    if (file) fd.append("images", file);
    fd.append("heat", heat === "inferno" && !canUseInferno(user) ? "fire" : heat);
    fd.append("adult_language", String(adult));
    if (comedyStyles.length) fd.append("comedy_styles", JSON.stringify(comedyStyles));
    try {
      const { data } = await api.post("/battle/generate", fd, { timeout: 180000 });
      setShow(data);
      refresh();
      openTheater();
    } catch (e) {
      if (!e?.response) {
        refresh();
        toast("Connection interrupted. Wait a moment and check Recent shows in Studio before retrying to avoid another paid battle.", "error");
      } else {
        toast("Battle failed: " + (e?.response?.data?.detail || e.message), "error");
      }
    } finally { setBusy(false); }
  };

  if (loadError) {
    return <div className="page-wrap" data-testid="battle-page"><ApiLoadError onRetry={() => setReload((n) => n + 1)}>Couldn't load battle access or fighters.</ApiLoadError></div>;
  }
  if (!access) return <div className="empty-state" data-testid="battle-page">Loading fighters…</div>;

  if (!access.unlocked) {
    return (
      <div className="page-wrap" data-testid="battle-locked">
        <div className="panel battle-locked">
          <h1 className="page-title">🥊 Roast Battle Mode</h1>
          <p className="page-sub">Pick two roasters, put them in the ring, and let the crowd decide who walks out alive. Live applause meter, round-by-round scoring and a winner reveal.</p>
          <button className="btn-primary" onClick={() => navigate("/credits")} data-testid="battle-unlock-btn">Unlock Roast Battle — $4.99</button>
        </div>
      </div>
    );
  }

  return (
    <div className="workspace battle-workspace" data-testid="battle-page">
      <div className="battle-controls workspace-scroll" aria-label="Battle setup and results" tabIndex={0}>
      <section className="panel">
        <h2>🥊 Set Up Your Battle</h2>
        <div className="label">Battle style</div>
        <div className="tier-toggle" role="group" aria-label="Battle style">
          {[['classic', 'Classic roast'], ['rap', 'Rap battle']].map(([id, label]) => (
            <button type="button" key={id} className={`tier-btn ${battleStyle === id ? "active" : ""}`}
              aria-pressed={battleStyle === id} onClick={() => setBattleStyle(id)} data-testid={`battle-style-${id}`}>
              <span className="tier-name">{label}</span>
            </button>
          ))}
        </div>
        {battleStyle === "rap" && <p className="hotseat-input-hint">Spoken-word verses over an original beat, not singing; timing is approximate. Fighter portraits may be analyzed with OpenAI vision, which may incur a separate charge. The writer receives observations, not portrait images, when using the two-stage writer. Existing Battle access and credit costs apply.</p>}
        <div className="label">Rounds</div>
        <div className="tier-toggle three">
          {[2, 3, 4].map((r) => (
            <button key={r} className={`tier-btn ${rounds === r ? "active" : ""}`} onClick={() => setRounds(r)} data-testid={`battle-rounds-${r}`}>
              <span className="tier-name">{r} rounds</span>
            </button>
          ))}
        </div>
        <div className="label">Heat & language</div>
        <HeatControls heat={heat} setHeat={setHeat} adult={adult} setAdult={setAdult} user={user}
          onLocked={() => { toast("Inferno is part of Brutality+ Mode 🔒", "error"); navigate("/credits"); }} />
        <ComedyStyles value={comedyStyles} onChange={setComedyStyles} />
        <div className="label">Optional: a victim they both roast</div>
        <input className="input" maxLength={120} placeholder="Name (optional)" value={subjectName} onChange={(e) => setSubjectName(e.target.value)} data-testid="battle-subject-input" />
        <textarea className="textarea" maxLength={3000} placeholder="Beef, backstory, inside jokes…" value={context} onChange={(e) => setContext(e.target.value)} data-testid="battle-context-input" />
        <p className="hotseat-input-hint">A fallback writer may receive your name, context, boundaries, and photo observations (not photos), and may cache responses. Skip sensitive details.</p>
        <label className="label" htmlFor="battle-boundaries">Off-limits topics <span className="hotseat-optional">optional</span></label>
        <input id="battle-boundaries" className="input" maxLength={600} placeholder="Anything the fighters should leave out" value={offLimits}
          onChange={(e) => setOffLimits(e.target.value)} data-testid="battle-off-limits-input" aria-describedby="battle-boundaries-hint" />
        <p className="hotseat-input-hint" id="battle-boundaries-hint">We'll ask the writer to avoid these topics; review generated content before sharing.</p>
        <label className="btn-secondary file-button" data-testid="battle-upload-btn">
          <input type="file" className="file-input-visually-hidden" accept="image/jpeg,image/png,image/webp" aria-label="Add battle photo" onChange={(e) => {
            const picked = e.target.files?.[0];
            if (picked) { const error = imageError(picked); if (error) toast(error, "error"); else setFile(picked); }
            e.target.value = "";
          }} data-testid="battle-image-input" />
          {file ? `📷 ${file.name}` : "📷 Add photo (optional)"}
        </label>
        <p className="hotseat-input-hint">Your setup stays while you navigate. For privacy, photos need to be reselected after a page refresh.</p>
        <button className="btn-primary battle-go" disabled={picks.length !== 2 || busy} onClick={fight} data-testid="battle-fight-btn">
          {busy ? "Writing the beef…" : `FIGHT! · ${cost} credits`}
        </button>
      </section>
      <section className="panel" ref={ringRef} data-testid="battle-ring">
        <h2>🎤 The Ring</h2>
        <Scoreboard a={a} b={b} live={live} result={revealed ? show?.battle : null} />
        {show && (
          <div className="show-actions">
            <button className="btn-primary" onClick={openTheater} data-testid="battle-replay-btn">▶ Watch the Battle</button>
            {!revealed && <button className="btn-ghost" onClick={() => { setTheater(false); setRevealed(true); }} data-testid="battle-skip-btn">Skip to winner</button>}
            <ShareButton roastId={show.roast_id} />
            <ReelButton roastId={show.roast_id} prepaid={user?.plan_tier === "vip" || user?.lifetime_founder} />
          </div>
        )}
        {busy && <div className="empty-state"><span className="spinner" /> The fighters are trash-talking backstage…</div>}
        {!busy && <ShowTranscript transcript={show?.transcript || []} personaById={byId} activeIdx={-1} emptyText="Pick two fighters and hit FIGHT." />}
      </section>
      </div>
      <section className="panel battle-roster workspace-scroll" aria-label="Choose battle fighters" tabIndex={0}>
        <h2>🥊 Pick Two Fighters <span className="comic-inspo">{picks.length}/2</span></h2>
        <PersonaBrowser personas={personas} selected={picks} onSelect={toggle} max={2} mode="battle" />
      </section>
      {theater && show && (
        <RoastTheater transcript={show.transcript} personaById={byId} images={show.images} subjectName={subjectName}
          mode="battle" battleStyle={show.battle_style} battle={show.battle} onBeatDone={onBeatDone} onFinish={() => setRevealed(true)}
          onClose={() => { setTheater(false); setRevealed(true); }} />
      )}
    </div>
  );
}

import "@/styles/workspace-split.css";
