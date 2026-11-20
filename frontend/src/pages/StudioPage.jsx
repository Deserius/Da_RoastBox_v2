import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";
import { crowd } from "@/lib/crowdEngine";
import { ShowTranscript } from "@/components/ShowTranscript";
import { ShareButton } from "@/components/ShareButton";
import { ReelButton } from "@/components/ReelButton";
import { RoastTheater } from "@/components/theater/RoastTheater";
import { StepPanel, Stepper } from "@/components/studio/StepPanel";
import { RosterPicker } from "@/components/studio/RosterPicker";
import { HotSeatForm } from "@/components/studio/HotSeatForm";
import { ComedyStyles } from "@/components/studio/ComedyStyles";
import { HeatControls, canUseInferno } from "@/components/studio/HeatControls";
import { useShowDraft } from "@/hooks/useShowDraft";
import ApiLoadError from "@/components/ApiLoadError";
import { imageError } from "@/lib/uploads";

const MAX_PERSONAS = 5;
const MAX_IMAGES = 4;

export default function StudioPage() {
  const { user, refresh } = useAuth();
  const { toast } = useToast();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const [personas, setPersonas] = useState([]);
  const [rosterError, setRosterError] = useState(false);
  const [reloadRoster, setReloadRoster] = useState(0);
  const [quoteError, setQuoteError] = useState(false);
  const [reloadQuote, setReloadQuote] = useState(0);
  const [selected, setSelected] = useShowDraft("studio.selected", []);
  const [images, setImages] = useShowDraft("studio.images", [], { memoryOnly: true });
  const [subjectName, setSubjectName] = useShowDraft("studio.subjectName", "");
  const [contextText, setContextText] = useShowDraft("studio.contextText", "");
  const [offLimits, setOffLimits] = useShowDraft("studio.offLimits", "");
  const [duration, setDuration] = useShowDraft("shared.duration", 3);
  const [heat, setHeat] = useShowDraft("shared.heat", canUseInferno(user) ? "inferno" : "fire");
  const [adult, setAdult] = useShowDraft("shared.adult", true);
  const [comedyStyles, setComedyStyles] = useShowDraft("shared.comedyStyles", []);
  const [roastTier, setRoastTier] = useShowDraft("studio.roastTier", "standard");
  const [usePremiumVoice, setUsePremiumVoice] = useShowDraft("studio.premiumVoice", false);
  const [hdExport, setHdExport] = useShowDraft("studio.hdExport", false);
  const [costQuote, setCostQuote] = useState(null);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null);
  const [theater, setTheater] = useState(false);
  const [recentShows, setRecentShows] = useState([]);
  const [historyError, setHistoryError] = useState(false);
  const [reloadHistory, setReloadHistory] = useState(0);

  useEffect(() => {
    if (heat === "inferno" && user && !canUseInferno(user)) setHeat("fire");
  }, [heat, user, setHeat]);

  useEffect(() => {
    let active = true;
    setRosterError(false);
    api.get("/personas").then(({ data }) => { if (active) setPersonas(data.personas || []); })
      .catch(() => { if (active) setRosterError(true); });
    return () => { active = false; };
  }, [user?.premium_personas_unlocked, user?.plan_tier, reloadRoster]);
  useEffect(() => {
    let active = true;
    setHistoryError(false);
    api.get("/roast/history").then(({ data }) => {
      if (active) setRecentShows((data.history || []).filter((show) => show.id && show.transcript?.length));
    }).catch(() => { if (active) setHistoryError(true); });
    return () => { active = false; };
  }, [user?.id, reloadHistory]);
  useEffect(() => {
    const pre = searchParams.get("persona");
    if (pre) setSelected((cur) => (cur.includes(pre) ? cur : [...cur, pre].slice(0, MAX_PERSONAS)));
  }, [searchParams, setSelected]);

  const personaById = useMemo(() => Object.fromEntries(personas.map((p) => [p.id, p])), [personas]);
  const ordered = useMemo(() => [...personas].sort((a, b) => Number(!!a.locked) - Number(!!b.locked)), [personas]);
  const hasPremiumPersona = selected.some((id) => personaById[id]?.is_premium);

  useEffect(() => {
    let active = true;
    setCostQuote(null);
    setQuoteError(false);
    api.get("/roast/cost-quote", { params: { roast_tier: roastTier, premium_voice: usePremiumVoice, premium_persona: hasPremiumPersona, hd_export: hdExport } })
      .then(({ data }) => { if (active) setCostQuote(data); })
      .catch(() => { if (active) setQuoteError(true); });
    return () => { active = false; };
  }, [roastTier, usePremiumVoice, hdExport, hasPremiumPersona, user?.credits, reloadQuote]);

  const togglePersona = (p) => {
    if (p.locked) { toast("Premium roaster — unlock the Premium Personas Bundle or VIP.", "error"); navigate("/credits"); return; }
    setSelected((cur) => {
      if (cur.includes(p.id)) return cur.filter((x) => x !== p.id);
      if (cur.length >= MAX_PERSONAS) { toast(`Max ${MAX_PERSONAS} roasters`, "error"); return cur; }
      return [...cur, p.id];
    });
  };
  const randomize = () => {
    const pool = [...personas.filter((p) => !p.locked)].sort(() => Math.random() - 0.5);
    setSelected(pool.slice(0, 2 + Math.floor(Math.random() * 3)).map((p) => p.id));
  };
  const onPick = (e) => {
    const files = Array.from(e.target.files || []).slice(0, MAX_IMAGES - images.length);
    const valid = files.filter((file) => { const error = imageError(file); if (error) toast(error, "error"); return !error; });
    setImages((c) => [...c, ...valid.map((file) => ({ file, previewUrl: URL.createObjectURL(file) }))].slice(0, MAX_IMAGES));
    e.target.value = "";
  };
  const onRemove = (idx) => setImages((c) => { const x = [...c]; URL.revokeObjectURL(x[idx]?.previewUrl); x.splice(idx, 1); return x; });

  const cost = costQuote?.credit_cost ?? 5;
  const free = !!costQuote?.free_available;
  const canPremiumVoice = user?.premium_voices_unlocked || ["plus", "vip"].includes(user?.plan_tier);
  const effectiveHeat = heat === "inferno" && !canUseInferno(user) ? "fire" : heat;

  const generate = async () => {
    if (!selected.length) return toast("Step 4: pick at least 1 roaster", "error");
    if (!images.length) return toast("Step 1: add at least 1 photo of the victim", "error");
    if (!free && (user?.credits ?? 0) < cost) { toast(`Need ${cost} credits, you have ${user?.credits ?? 0}`, "error"); navigate("/credits"); return; }
    crowd.unlock();
    setBusy(true); setResult(null); setTheater(false);
    const fd = new FormData();
    fd.append("persona_ids", selected.join(","));
    if (subjectName.trim()) fd.append("subject_name", subjectName.trim());
    if (contextText.trim()) fd.append("user_context", contextText.trim());
    if (offLimits.trim()) fd.append("off_limits", offLimits.trim());
    fd.append("duration_minutes", String(duration));
    fd.append("roast_tier", roastTier);
    fd.append("use_premium_voice", String(usePremiumVoice));
    fd.append("hd_export", String(hdExport));
    fd.append("heat", effectiveHeat);
    fd.append("adult_language", String(adult));
    if (comedyStyles.length) fd.append("comedy_styles", JSON.stringify(comedyStyles));
    images.forEach((im) => fd.append("images", im.file));
    try {
      const { data } = await api.post("/roast/generate", fd, { timeout: 240000 });
      setResult({ ...data, hd: hdExport, subjectName: subjectName.trim(), personaIds: data.persona_ids || selected });
      setTheater(true);
      setReloadHistory((n) => n + 1);
      refresh();
      toast(data.was_free_roast ? "Daily free roast used ✨" : `-${data.credits_spent} credits · ${data.credits_remaining} left`, "success");
    } catch (e) {
      if (!e?.response) {
        setReloadHistory((n) => n + 1); refresh();
        toast("Connection interrupted. Wait a moment and check Recent shows before retrying to avoid another paid show.", "error");
      } else {
        toast("Roast failed: " + (e?.response?.data?.detail || e.message), "error");
      }
    } finally { setBusy(false); }
  };

  const watchRecent = (show, playShow = true) => {
    if (playShow) crowd.unlock();
    setResult({
      roast_id: show.id,
      transcript: show.transcript,
      images: Array.from({ length: Math.min(4, Math.max(0, show.image_count || 0)) }, (_, i) => `/api/media/subject/${show.id}/${i}.jpg`),
      subjectName: show.subject_name,
      personaIds: show.persona_ids,
      mode: show.mode || "roast",
      battle: show.battle,
      battle_style: show.battle_style || "classic",
      hd: show.hd_export,
      reelRequested: !playShow,
    });
    setTheater(playShow);
    if (!playShow) requestAnimationFrame(() => document.querySelector('[data-testid="results-panel"]')?.scrollIntoView({ block: "start", behavior: "smooth" }));
  };

  const steps = [
    { label: "Hot Seat", target: "step-hotseat", done: images.length > 0 },
    { label: "Heat", target: "step-heat", done: true },
    { label: "Showtime", target: "step-showtime", done: !!result },
    { label: "Lineup", target: "step-lineup", done: selected.length > 0 },
  ];

  return (
    <div className="studio" data-testid="roast-studio">
      {rosterError && <ApiLoadError onRetry={() => setReloadRoster((n) => n + 1)}>Couldn't load the roaster lineup.</ApiLoadError>}
      <Stepper steps={steps} />
      <div className="workspace studio-grid">
        <section className="studio-side workspace-scroll" aria-label="Roast setup" tabIndex={0}>
      {(recentShows.length > 0 || historyError) && (
        <details className="panel recent-shows" data-testid="recent-shows">
          <summary>Recent shows <span>· Watch again without spending credits</span></summary>
          {historyError && <ApiLoadError onRetry={() => setReloadHistory((n) => n + 1)}>Couldn't load recent shows.</ApiLoadError>}
          <div className="recent-show-list">
            {recentShows.map((show) => (
              <div className="recent-show" key={show.id} data-testid={`recent-show-${show.id}`}>
                <div>
                  <strong>{show.mode === "battle" ? "🥊 Battle" : "🔥 Roast"}{show.subject_name ? ` · ${show.subject_name}` : ""}</strong>
                  <small>{show.created_at ? new Date(show.created_at).toLocaleString() : "Saved show"}</small>
                </div>
                <div className="recent-show-actions">
                  <button type="button" className="btn-secondary" onClick={() => watchRecent(show)}>▶ Watch again</button>
                  <button type="button" className="btn-ghost" onClick={() => watchRecent(show, false)} data-testid={`recent-reels-${show.id}`}>🎬 Reels</button>
                </div>
              </div>
            ))}
          </div>
        </details>
      )}

          <StepPanel n={1} title="The Hot Seat" hint="Who's getting roasted?" done={images.length > 0} testid="step-hotseat">
            <HotSeatForm subjectName={subjectName} setSubjectName={setSubjectName} contextText={contextText} setContextText={setContextText}
              offLimits={offLimits} setOffLimits={setOffLimits} images={images} onPick={onPick} onRemove={onRemove} max={MAX_IMAGES} />
          </StepPanel>

          <StepPanel n={2} title="Heat & Language" hint="How disrespectful are we getting?" done testid="step-heat">
            <HeatControls heat={effectiveHeat} setHeat={setHeat} adult={adult} setAdult={setAdult} user={user}
              onLocked={() => { toast("Inferno is part of Brutality+ Mode 🔒", "error"); navigate("/credits"); }}
              afterHeat={<>
              <div className="heat-head" style={{ marginTop: 14 }}>
              <span className="label" style={{ margin: 0 }}>Set length</span>
              <span className="heat-value" data-testid="duration-value">{duration} min</span>
            </div>
            <input type="range" min={3} max={10} step={1} value={duration} onChange={(e) => setDuration(parseInt(e.target.value, 10))}
              className="duration-slider" data-testid="duration-slider" aria-label="Set length in minutes" />
              </>} />
            <ComedyStyles value={comedyStyles} onChange={setComedyStyles} />

          </StepPanel>

          <StepPanel n={3} title="Showtime" hint="Extras & checkout" done={!!result} testid="step-showtime">
            <div className="tier-toggle" data-testid="tier-toggle">
              <button className={`tier-btn ${roastTier === "standard" ? "active" : ""}`} onClick={() => setRoastTier("standard")} data-testid="tier-standard-btn">
                <div className="tier-name">Standard</div><div className="tier-cost">5 credits</div>
              </button>
              <button className={`tier-btn premium ${roastTier === "premium" ? "active" : ""}`} onClick={() => setRoastTier("premium")} data-testid="tier-premium-btn">
                <div className="tier-name">⭐ Premium</div><div className="tier-cost">10 · headline writing</div>
              </button>
            </div>
            <label className={`addon-row ${!canPremiumVoice ? "disabled" : ""}`} data-testid="premium-voice-row">
              <input type="checkbox" checked={usePremiumVoice} disabled={!canPremiumVoice} onChange={(e) => setUsePremiumVoice(e.target.checked)} data-testid="premium-voice-toggle" />
              <div><div className="addon-name">🎙️ Premium HD Voices</div><div className="addon-tagline">{canPremiumVoice ? "+3 credits" : "Locked — Voice Bundle or Plus/VIP"}</div></div>
            </label>
            <label className="addon-row" data-testid="hd-export-row">
              <input type="checkbox" checked={hdExport} onChange={(e) => setHdExport(e.target.checked)} data-testid="hd-export-toggle" />
              <div><div className="addon-name">🎬 Prepay HD Reels</div><div className="addon-tagline">+5 credits · free 30s & 60s highlight reels for this roast</div></div>
            </label>
            <div className="cost-summary" data-testid="cost-summary">
              <div className="cost-headline" style={free ? { color: "var(--accent-alt)" } : {}}>{!costQuote ? (quoteError ? "Quote unavailable" : "Calculating…") : free ? "FREE — Daily Roast" : `${cost} credits`}</div>
              <div className="cost-sub">Balance: <strong>{user?.credits ?? 0}</strong></div>
            </div>
            {quoteError && <ApiLoadError onRetry={() => setReloadQuote((n) => n + 1)}>Couldn't get the current roast cost.</ApiLoadError>}
            <button className="btn-primary roast-go" onClick={generate} disabled={busy || !costQuote} data-testid="generate-roast-btn">
              {busy ? <><span className="spinner" /> Writing a {duration}-minute set…</> : !costQuote ? "Checking cost…" : `🔥 ROAST 'EM — ${free ? "FREE" : `${cost} credits`}`}
            </button>
          </StepPanel>
      {(busy || result) && (
        <div className="panel results-panel" data-testid="results-panel">
          <div className="results-head">
            <h2 style={{ margin: 0 }}>🎤 The Set</h2>
            {result && (
              <div className="show-actions">
                <button className="btn-primary" onClick={() => setTheater(true)} data-testid="watch-theater-btn">▶ Watch the Show</button>
                <ShareButton roastId={result.roast_id} />
                <ReelButton key={result.roast_id} roastId={result.roast_id} autoOpen={!!result.reelRequested}
                  prepaid={result.hd || user?.is_preview || user?.plan_tier === "vip" || user?.lifetime_founder} />
              </div>
            )}
          </div>
          {busy ? <div className="empty-state"><span className="spinner" /> The roasters are writing backstage…</div>
            : <ShowTranscript transcript={result.transcript} personaById={personaById} activeIdx={-1} />}
        </div>
      )}

        </section>
        <section className="studio-roster workspace-scroll" aria-label="Choose roasters" tabIndex={0}>
          <StepPanel n={4} title="Pick Your Roasters" hint={`Up to ${MAX_PERSONAS} comics on the dais`} done={selected.length > 0} testid="step-lineup">
            <RosterPicker personas={ordered} selected={selected} onToggle={togglePersona} onRandom={randomize} max={MAX_PERSONAS} />
          </StepPanel>
        </section>

      </div>

      {theater && result && (
        <RoastTheater transcript={result.transcript} personaById={personaById} images={result.images} lineupIds={result.personaIds}
          subjectName={result.subjectName} mode={result.mode || "roast"} battleStyle={result.battle_style} battle={result.battle} onClose={() => setTheater(false)} />
      )}
    </div>
  );
}

import "@/styles/workspace-split.css";
