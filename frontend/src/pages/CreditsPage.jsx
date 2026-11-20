import { useEffect, useState } from "react";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import { useToast } from "@/lib/ToastContext";
import ApiLoadError from "@/components/ApiLoadError";

const SECTION_ORDER = [
  { key: "subscriptions", title: "🔁 30-Day Passes", icon: "🔁",
    types: ["plus_subscription", "vip_subscription"],
    blurb: "One-time purchase for 30 days. These passes do not renew automatically." },
  { key: "credits", title: "🔥 Credit Packs", icon: "🔥",
    types: ["credits"],
    blurb: "Credits never expire. The bigger the pack, the better the rate." },
  { key: "addons", title: "⭐ One-Time Add-Ons", icon: "⭐",
    types: ["premium_personas", "premium_voices", "roast_battle", "nsfw_edgier"],
    blurb: "Permanent unlocks. Buy once, keep forever." },
  { key: "founder", title: "👑 Lifetime Founder", icon: "👑",
    types: ["lifetime_founder"],
    blurb: "Everything. Forever. One payment. Founder status." },
];

export default function CreditsPage() {
  const [packs, setPacks] = useState([]);
  const [roastCosts, setRoastCosts] = useState({});
  const [busy, setBusy] = useState("");
  const [loadError, setLoadError] = useState(false);
  const [reload, setReload] = useState(0);
  const { user } = useAuth();
  const { toast } = useToast();

  useEffect(() => {
    let active = true;
    setLoadError(false);
    api.get("/payments/packs").then(({ data }) => {
      if (active) { setPacks(data.packs || []); setRoastCosts(data.roast_costs || {}); }
    }).catch(() => { if (active) setLoadError(true); });
    return () => { active = false; };
  }, [reload]);

  const buy = async (pack_id) => {
    setBusy(pack_id);
    try {
      const { data } = await api.post("/payments/checkout", {
        pack_id,
        origin_url: window.location.origin,
      });
      if (data?.checkout_url) {
        window.location.href = data.checkout_url;
      } else {
        toast("Checkout init failed", "error");
      }
    } catch (e) {
      toast("Checkout failed: " + (e?.response?.data?.detail || e.message), "error");
    } finally {
      setBusy("");
    }
  };

  const isOwned = (p) => {
    if (p.type === "premium_personas") return !!user?.premium_personas_unlocked;
    if (p.type === "premium_voices") return !!user?.premium_voices_unlocked;
    if (p.type === "roast_battle") return !!user?.roast_battle_unlocked;
    if (p.type === "nsfw_edgier") return !!user?.nsfw_edgier_unlocked;
    if (p.type === "lifetime_founder") return !!user?.lifetime_founder;
    return false;
  };

  const planTier = user?.plan_tier || "free";
  const planActive = ["plus", "vip"].includes(planTier) && user?.plan_until && new Date(user.plan_until) > new Date();
  const isVip = planTier === "vip" && planActive;

  return (
    <div className="workspace" style={{ gridTemplateColumns: "1fr" }} data-testid="credits-page">
      <div className="panel" style={{ maxWidth: 1180, margin: "0 auto", width: "100%" }}>
        <h2>🔥 Stock Up & Unlock the Full Experience</h2>
        <p className="text-muted">
          30-day passes · credit packs · add-ons · Founder Pack for legends.
        </p>
        {user?.is_preview && <p role="status" data-testid="preview-checkout-notice" className="text-muted" style={{ fontSize: 13 }}>
          Purchases are disabled for disposable preview accounts. Real checkout also requires the owner's Stripe configuration.
        </p>}
        {loadError && <ApiLoadError onRetry={() => setReload((n) => n + 1)}>Couldn't load the product catalog.</ApiLoadError>}

        <div className="balance-row" data-testid="balance-row">
          <div className="balance-tile">
            <div className="balance-label">Credits</div>
            <div className="balance-value">{user?.credits ?? 0}</div>
            <div className="balance-sub">never expire</div>
          </div>
          <div className="balance-tile">
            <div className="balance-label">Plan</div>
            <div className="balance-value" style={{ color: isVip || planActive ? "var(--accent-alt)" : "var(--text-soft)" }}>
              {planActive ? (isVip ? "VIP" : "Plus") : "Free"}
            </div>
            {planActive && (
              <div className="balance-sub" data-testid="plan-expiry">
                expires {new Date(user.plan_until).toLocaleDateString()}
              </div>
            )}
          </div>
          <div className="balance-tile">
            <div className="balance-label">Premium Personas</div>
            <div className="balance-value">{user?.premium_personas_unlocked || isVip ? "✓" : "—"}</div>
            {isVip && !user?.premium_personas_unlocked && <div className="balance-sub">included with VIP</div>}
          </div>
          <div className="balance-tile">
            <div className="balance-label">Premium Voices</div>
            <div className="balance-value">{user?.premium_voices_unlocked || planActive ? "✓" : "—"}</div>
            {planActive && !user?.premium_voices_unlocked && <div className="balance-sub">included with pass</div>}
          </div>
          <div className="balance-tile">
            <div className="balance-label">Founder</div>
            <div className="balance-value">{user?.lifetime_founder ? "👑" : "—"}</div>
          </div>
        </div>

        {/* Cost table */}
        <div className="cost-table" data-testid="cost-table">
          <div className="cost-table-title">How credits are spent</div>
          <div className="cost-table-grid">
            <div className="cost-row"><span>Standard Roast</span><span className="cost-val">{roastCosts.standard_roast ?? 5} credits</span></div>
            <div className="cost-row"><span>Premium Roast</span><span className="cost-val">{roastCosts.premium_roast ?? 10} credits</span></div>
            <div className="cost-row"><span>Premium Voice</span><span className="cost-val">+{roastCosts.premium_voice ?? 3}</span></div>
            <div className="cost-row"><span>Premium Persona</span><span className="cost-val">+{roastCosts.premium_persona ?? 5}</span></div>
            <div className="cost-row"><span>HD Video Export</span><span className="cost-val">+{roastCosts.hd_export ?? 5}</span></div>
            <div className="cost-row free"><span>Daily Free Roast</span><span className="cost-val">FREE · 1 per day</span></div>
          </div>
        </div>

        {SECTION_ORDER.map((sec) => {
          const items = packs.filter((p) => sec.types.includes(p.type));
          if (items.length === 0) return null;
          return (
            <div key={sec.key} className="section-block" data-testid={`section-${sec.key}`}>
              <h3 className="section-title">{sec.title}</h3>
              <p className="text-muted" style={{ fontSize: 13, margin: "0 0 12px" }}>{sec.blurb}</p>
              <div className="packs-grid">
                {items.map((p) => {
                  const owned = isOwned(p);
                  const featured = p.highlight;
                  return (
                    <div
                      key={p.id}
                      className={`pack-card ${featured ? "featured" : ""} ${owned ? "owned" : ""} ${p.type === "lifetime_founder" ? "founder" : ""}`}
                      data-testid={`pack-${p.id}`}
                    >
                      {featured && <div className="pack-ribbon">⭐ POPULAR</div>}
                      <div className="pack-title">{p.name}</div>
                      {p.tagline && <div className="pack-tagline">{p.tagline}</div>}
                      {p.perks && p.perks.length > 0 && (
                        <ul className="pack-perks" data-testid={`perks-${p.id}`}>
                          {p.perks.map((perk, i) => <li key={i}>✓ {perk}</li>)}
                        </ul>
                      )}
                      {p.type === "credits" && (
                        <div className="pack-credits">{p.credits}<span> credits</span></div>
                      )}
                      {(p.type === "plus_subscription" || p.type === "vip_subscription") && (
                        <div className="pack-credits">{p.credits}<span> credits</span></div>
                      )}
                      <div className="pack-price">
                        ${p.amount_usd.toFixed(2)}
                        {(p.type === "plus_subscription" || p.type === "vip_subscription") && <span className="price-period"> / 30 days</span>}
                      </div>
                      <button
                        className="btn-primary"
                        onClick={() => buy(p.id)}
                        disabled={busy === p.id || owned || user?.is_preview}
                        style={{ width: "100%" }}
                        data-testid={`buy-${p.id}-btn`}
                      >
                        {owned ? "Owned"
                          : user?.is_preview ? "Unavailable in preview"
                          : busy === p.id ? "Redirecting…"
                          : p.type === "plus_subscription" || p.type === "vip_subscription" ? "Buy 30-Day Pass"
                          : p.type === "credits" ? "Buy Pack"
                          : p.type === "lifetime_founder" ? "Become a Founder"
                          : "Unlock"}
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}

        <p className="text-muted" style={{ marginTop: 24, fontSize: 12, textAlign: "center" }}>
          Payments are processed by Stripe when checkout is configured.
        </p>
      </div>
    </div>
  );
}
