import { useEffect, useRef, useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";

const POLL_INTERVAL = 2000;
const MAX_POLLS = 8;

export default function CheckoutSuccess() {
  const [params] = useSearchParams();
  const sessionId = params.get("session_id");
  const navigate = useNavigate();
  const { refresh } = useAuth();
  const [state, setState] = useState({ status: sessionId ? "checking" : "error", error: sessionId ? "" : "No checkout session was supplied.", credits_added: 0, balance: 0, pack_type: "credits", pack_name: "" });
  const polls = useRef(0);

  useEffect(() => {
    if (!sessionId) return;
    let timer;
    const poll = async () => {
      try {
        const { data } = await api.get(`/payments/status/${sessionId}`);
        if (data.payment_status === "paid") {
          await refresh();
          setState({
            status: "paid",
            credits_added: data.credits_added,
            balance: data.credits_balance,
            pack_type: data.pack_type,
            pack_name: data.pack_name,
            premium_personas: data.premium_personas_unlocked,
            premium_voices: data.premium_voices_unlocked,
            roast_battle: data.roast_battle_unlocked,
            nsfw_edgier: data.nsfw_edgier_unlocked,
            lifetime_founder: data.lifetime_founder,
            plan_tier: data.plan_tier,
            plan_until: data.plan_until,
          });
          return;
        }
        if (data.payment_status === "expired" || data.payment_status === "failed") {
          setState({ status: "failed" }); return;
        }
        polls.current++;
        if (polls.current >= MAX_POLLS) { setState({ status: "timeout" }); return; }
        timer = setTimeout(poll, POLL_INTERVAL);
      } catch (e) {
        setState({ status: "error", error: e?.response?.data?.detail || e.message });
      }
    };
    poll();
    return () => clearTimeout(timer);
  }, [sessionId, refresh]);

  const renderPaid = () => {
    const t = state.pack_type;
    if (t === "premium_personas") return <h2>⭐ Premium Personas Unlocked!</h2>;
    if (t === "premium_voices")   return <h2>🎙️ Premium Voices Unlocked!</h2>;
    if (t === "roast_battle")     return <h2>⚔️ Roast Battle Mode Unlocked!</h2>;
    if (t === "nsfw_edgier")      return <h2>🔥 Brutality+ Mode Unlocked!</h2>;
    if (t === "lifetime_founder") return <h2>👑 Welcome, Founder! Everything unlocked forever.</h2>;
    if (t === "plus_subscription") return <h2>🎉 RoastBox Plus Active{state.plan_until ? ` — through ${new Date(state.plan_until).toLocaleDateString()}` : ""}!</h2>;
    if (t === "vip_subscription") return <h2>👑 RoastBox VIP Active{state.plan_until ? ` — through ${new Date(state.plan_until).toLocaleDateString()}` : ""}!</h2>;
    return <>
      <h2>🔥 +{state.credits_added} credits added!</h2>
      <p>Balance: <strong>{state.balance}</strong> credits</p>
    </>;
  };

  return (
    <div className="workspace" style={{ gridTemplateColumns: "1fr" }} data-testid="checkout-success">
      <div className="panel" style={{ maxWidth: 540, margin: "40px auto", textAlign: "center" }}>
        {state.status === "checking" && <><div className="spinner" /> <p>Confirming your payment…</p></>}
        {state.status === "paid" && (
          <>
            {renderPaid()}
            <button className="btn-primary" onClick={() => navigate("/studio")} data-testid="goto-studio-btn">Start Roasting</button>
          </>
        )}
        {state.status === "failed" && <>
          <h2>Payment Failed</h2>
          <button className="btn-secondary" onClick={() => navigate("/credits")} data-testid="retry-btn">Try Again</button>
        </>}
        {state.status === "timeout" && <>
          <p>Still processing. Refresh the page in a minute or check Settings.</p>
          <button className="btn-secondary" onClick={() => navigate("/credits")}>Back</button>
        </>}
        {state.status === "error" && <>
          <p role="alert" className="text-accent">Error: {state.error}</p>
          <button className="btn-secondary" onClick={() => navigate("/credits")}>Back to Packs</button>
        </>}
      </div>
    </div>
  );
}
