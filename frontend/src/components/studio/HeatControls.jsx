const HEATS = [
  { id: "mild", label: "Mild", icon: "🌶️", blurb: "Playful teasing — they'll leave smiling" },
  { id: "hot", label: "Hot", icon: "🌶️🌶️", blurb: "A real roast — sharp jabs with a wink" },
  { id: "fire", label: "Fire", icon: "🔥", blurb: "Brutal & personal — the crowd gasps" },
  { id: "inferno", label: "Inferno", icon: "🌋", blurb: "Maximum disrespect, uncut — within your boundaries" },
];

export const canUseInferno = (user) => !!(user?.nsfw_edgier_unlocked || user?.lifetime_founder);

export const HeatControls = ({ heat, setHeat, adult, setAdult, user, onLocked, afterHeat }) => {
  const idx = Math.max(0, HEATS.findIndex((h) => h.id === heat));
  const current = HEATS[idx];
  const infernoOk = canUseInferno(user);

  const onSlide = (e) => {
    const next = HEATS[parseInt(e.target.value, 10)];
    if (next.id === "inferno" && !infernoOk) { onLocked?.(); return; }
    setHeat(next.id);
  };

  return (
    <div className="heat-controls" data-testid="heat-controls">
      <div className="heat-head">
        <span className="label" style={{ margin: 0 }}>Roast heat</span>
        <span className={`heat-value heat-${current.id}`} data-testid="heat-value">{current.icon} {current.label}</span>
      </div>
      <input
        type="range" min={0} max={3} step={1} value={idx} onChange={onSlide}
        className={`heat-slider heat-${current.id}`} data-testid="heat-slider" aria-label="Roast heat"
      />
      <div className="heat-ticks">
        {HEATS.map((h, i) => (
          <button key={h.id} type="button" className={`heat-tick ${i === idx ? "active" : ""}`} data-testid={`heat-${h.id}-btn`}
            onClick={() => onSlide({ target: { value: i } })}>
            {h.label}{h.id === "inferno" && !infernoOk ? " 🔒" : ""}
          </button>
        ))}
      </div>
      <div className="heat-blurb" data-testid="heat-blurb">{current.blurb}</div>

      {afterHeat}
      <label className={`adult-toggle ${adult ? "on" : ""}`} data-testid="adult-language-row">
        <input type="checkbox" checked={adult} onChange={(e) => setAdult(e.target.checked)} data-testid="adult-language-toggle" />
        <span className="switch" aria-hidden="true"><span /></span>
        <span>
          <span className="addon-name">🔞 Adult language & 18+ jokes</span>
          <span className="addon-tagline">{adult ? "ON — profanity, sex jokes, uncut" : "OFF — clean but still savage"}</span>
        </span>
      </label>
    </div>
  );
};
