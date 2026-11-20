import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import * as Dialog from "@radix-ui/react-dialog";
import { ChevronDown, ChevronRight, CircleHelp, CreditCard, Facebook, Flame, Home, Instagram,
  LogOut, Menu, Mic2, Music2, Settings, ShoppingBag, Swords, Youtube, X } from "lucide-react";
import api from "@/lib/api";
import AboutAuthor from "@/components/AboutAuthor";
import { LoungeControl } from "@/lib/LoungeContext";
import "@/styles/account-menu.css";

const SOCIAL_LINKS = [
  { label: "Instagram", url: "https://www.instagram.com/", Icon: Instagram },
  { label: "Facebook", url: "https://www.facebook.com/", Icon: Facebook },
  { label: "TikTok", url: "https://www.tiktok.com/", Icon: Music2 },
  { label: "YouTube", url: "https://www.youtube.com/", Icon: Youtube },
];
const supportEmail = (process.env.REACT_APP_SUPPORT_EMAIL || "").trim();
const validSupportEmail = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i.test(supportEmail);

function displayDate(value) {
  if (!value) return "Date unavailable";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "Date unavailable" : date.toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
}
function displayAmount(value) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "Amount unavailable";
  return new Intl.NumberFormat(undefined, { style: "currency", currency: "USD" }).format(Number(value));
}
function readable(value) {
  if (typeof value !== "string" || !value) return "Unknown";
  return value.replace(/[_-]+/g, " ").replace(/^./, (s) => s.toUpperCase());
}
function initials(value) {
  return (value || "Guest").trim().split(/\s+/).slice(0, 2).map((word) => word[0]).join("").toUpperCase() || "G";
}

export default function AccountMenu({ user, logout, onDownload, downloading = false }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [activity, setActivity] = useState(null);
  const [activityState, setActivityState] = useState("idle");
  const requestRef = useRef(null);
  const userId = user?.id;

  useEffect(() => {
    // Never retain another user's account history across a session change.
    requestRef.current?.abort();
    requestRef.current = null;
    setActivity(null);
    setActivityState("idle");
    return () => requestRef.current?.abort();
  }, [userId]);

  const closeMenu = () => {
    requestRef.current?.abort();
    requestRef.current = null;
    setActivity(null);
    setActivityState("idle");
    setOpen(false);
  };
  const onOpenChange = (next) => { if (next) setOpen(true); else closeMenu(); };
  const loadActivity = () => {
    if (activityState === "ready" || requestRef.current) return;
    const request = new AbortController();
    requestRef.current = request;
    setActivityState("loading");
    api.get("/payments/activity", { signal: request.signal }).then(({ data }) => {
      if (!request.signal.aborted) { setActivity(data); setActivityState("ready"); }
    }).catch(() => {
      if (!request.signal.aborted) setActivityState("error");
    }).finally(() => { if (requestRef.current === request) requestRef.current = null; });
  };
  const go = (path) => { closeMenu(); navigate(path); };
  const name = user?.name?.trim() || (user?.is_preview ? "Preview Guest" : user?.email?.split("@")[0]) || "Guest";
  const nav = [
    { title: "Roast Studio", path: "/studio", Icon: Home, id: "studio" },
    { title: "Roasters", path: "/roasters", Icon: Mic2, id: "roasters" },
    { title: "Battle", path: "/battle", Icon: Swords, id: "battle" },
    { title: "Buy Credits", path: "/credits", Icon: ShoppingBag, id: "credits" },
    { title: "Settings", path: "/settings", Icon: Settings, id: "settings" },
  ];
  const status = () => {
    if (activityState === "loading" || activityState === "idle") return <p className="account-hint" role="status">Loading account activity…</p>;
    if (activityState === "error") return <p className="account-hint" role="alert">Couldn't load history. <button type="button" className="account-retry" onClick={loadActivity}>Try again</button></p>;
    return null;
  };
  const onToggle = (event) => { if (event.currentTarget.open) loadActivity(); };

  return (
    <div className="account-menu-root">
      <Dialog.Root open={open} onOpenChange={onOpenChange}>
        <Dialog.Trigger asChild>
          <button type="button" className="account-menu-toggle" aria-label="Open account and navigation menu" data-testid="menu-toggle"><Menu size={22} aria-hidden="true" /></button>
        </Dialog.Trigger>
        <Dialog.Portal>
          <Dialog.Overlay className="account-overlay" data-testid="account-menu-overlay" />
          <Dialog.Content className="account-drawer" data-testid="account-menu">
            <div className="account-drawer-top">
              <div>
                <div className="account-overline"><Flame size={13} aria-hidden="true" /> DA ROASTBOX</div>
                <Dialog.Title className="account-title">Your backstage<span>.</span></Dialog.Title>
                <Dialog.Description className="account-description">Your account, your history, and the rest of the show.</Dialog.Description>
              </div>
              <Dialog.Close asChild><button type="button" className="account-close" aria-label="Close menu" data-testid="menu-close"><X size={21} aria-hidden="true" /></button></Dialog.Close>
            </div>

            <section className="account-profile" aria-label="Your profile">
              <div className="account-profile-head">
                <div className="account-avatar" aria-hidden="true">{initials(name)}</div>
                <div className="account-identity">
                  <span className="account-eyebrow">{user?.is_preview ? "PREVIEW ACCOUNT" : "SIGNED IN AS"}</span>
                  <strong data-testid="menu-profile-name">{name}</strong>
                  <small>{user?.is_preview ? "Isolated guest account" : user?.email || "Account"}</small>
                </div>
              </div>
              <div className="account-stats">
                <div><span>CREDIT BALANCE</span><strong data-testid="menu-credit-balance">{user?.credits ?? 0} <small>credits</small></strong></div>
                <div><span>PLAN</span><strong>{user?.lifetime_founder ? "Founder" : readable(user?.plan_tier || "free")}</strong></div>
              </div>
            </section>

            <section className="account-section" aria-label="Navigation">
              <div className="account-section-label"><span>EXPLORE</span><i /></div>
              <div className="account-links">
                {nav.map(({ title, path, Icon, id }) => <button type="button" className="account-link" key={path} onClick={() => go(path)} data-testid={`menu-nav-${id}`}>
                  <span><Icon size={17} aria-hidden="true" /> {title}</span><ChevronRight size={16} aria-hidden="true" />
                </button>)}
                <AboutAuthor className="account-about-link" testId="menu-about-developer-btn" />
                {process.env.REACT_APP_SOURCE_DOWNLOAD_ENABLED === "true" && <button type="button" className="account-link" onClick={() => { closeMenu(); onDownload(); }} disabled={downloading} data-testid="menu-source-download">
                  <span>⬇ {downloading ? "Zipping…" : "Download source"}</span><ChevronRight size={16} aria-hidden="true" />
                </button>}
              </div>
            </section>

            <section className="account-section" aria-label="Lounge audio">
              <div className="account-section-label"><span>SET THE MOOD</span><i /></div>
              <div style={{ marginTop: 9 }}><LoungeControl /></div>
            </section>

            <section className="account-section" aria-label="Account history">
              <div className="account-section-label"><span>YOUR ACCOUNT</span><i /></div>
              <details className="account-details" onToggle={onToggle} data-testid="payment-history-section">
                <summary><span><CreditCard size={17} aria-hidden="true" /><span>Payment history<small>Recent purchases &amp; status</small></span></span><ChevronDown size={16} aria-hidden="true" /></summary>
                <div className="account-details-body" data-testid="payment-history">
                  {status()}
                  {activityState === "ready" && (activity?.payments?.length ? <>
                    <p className="account-hint">Last {activity.limit} records stored by Da RoastBox. Payment status may take time to update.</p>
                    <ul className="account-history-list">{activity.payments.map((item, index) => <li key={item.id || `${item.created_at}-${index}`}>
                      <div><strong>{item.product_name || "Purchase"}</strong><span>{displayDate(item.created_at)} · {readable(item.payment_status)}</span></div>
                      <b>{displayAmount(item.amount_usd)}</b>
                    </li>)}</ul>
                  </> : <p className="account-hint">No payment history yet.{user?.is_preview ? " Purchases are disabled in preview." : ""}</p>)}
                </div>
              </details>
              <details className="account-details" onToggle={onToggle} data-testid="usage-history-section">
                <summary><span><Flame size={17} aria-hidden="true" /><span>Usage history<small>Recent shows &amp; credit activity</small></span></span><ChevronDown size={16} aria-hidden="true" /></summary>
                <div className="account-details-body" data-testid="usage-history">
                  {status()}
                  {activityState === "ready" && <>
                    {!activity?.shows?.length && !activity?.credit_activity?.length && <p className="account-hint">No usage history yet. Your recent shows and credit activity will appear here.</p>}
                    {!!activity?.shows?.length && <>
                      <h4>RECENT SHOWS</h4><ul className="account-history-list">{activity.shows.map((show, index) => <li key={show.id || `${show.created_at}-${index}`}>
                        <div><strong>{show.mode === "battle" ? "Battle" : "Roast"}{show.subject_name ? ` · ${show.subject_name}` : ""}</strong><span>{displayDate(show.created_at)}</span></div>
                        <b>{show.was_free_roast ? "Free" : typeof show.credits_spent === "number" ? `${show.credits_spent} cr` : "—"}</b>
                      </li>)}</ul>
                      <button type="button" className="account-inline-action" onClick={() => go("/studio")}>Open Studio for replays <ChevronRight size={14} aria-hidden="true" /></button>
                    </>}
                    {!!activity?.credit_activity?.length && <>
                      <h4>CREDIT ACTIVITY</h4><ul className="account-history-list">{activity.credit_activity.map((entry, index) => <li key={entry.id || `${entry.created_at}-${index}`}>
                        <div><strong>{entry.description || readable(entry.type)}</strong><span>{displayDate(entry.created_at)}</span></div>
                        <b>{typeof entry.amount === "number" ? `${entry.amount > 0 ? "+" : ""}${entry.amount} cr` : "—"}</b>
                      </li>)}</ul>
                    </>}
                    <p className="account-hint">Showing up to {activity.limit} of each. Some refunds may not appear in credit activity; your current balance is authoritative.</p>
                  </>}
                </div>
              </details>
              <details className="account-details" data-testid="help-section">
                <summary><span><CircleHelp size={17} aria-hidden="true" /><span>Help &amp; developer contact<small>Get a hand with Da RoastBox</small></span></span><ChevronDown size={16} aria-hidden="true" /></summary>
                <div className="account-details-body">
                  <p className="account-hint">Pick your roasters, add a photo, set your heat, and start the show. Your saved shows can be replayed from Studio.</p>
                  <button type="button" className="account-inline-action" onClick={() => go("/settings")}>Open app settings <ChevronRight size={14} aria-hidden="true" /></button>
                  {validSupportEmail ? <p className="account-hint">Need more help? <a href={`mailto:${supportEmail}`}>Contact the developer</a></p>
                    : <p className="account-hint">Direct developer contact details haven't been set up yet.</p>}
                </div>
              </details>
            </section>

            <section className="account-section account-socials" aria-label="Social links">
              <div className="account-section-label"><span>FIND US</span><i /></div>
              <p className="account-hint">These open the platform homepages for now—not official Da RoastBox profiles.</p>
              <div className="account-social-row">{SOCIAL_LINKS.map(({ label, url, Icon }) => <a key={label} href={url} target="_blank" rel="noopener noreferrer" aria-label={`${label} platform homepage; not an official profile`} title={`${label} homepage (placeholder, not an official profile)`}><Icon size={17} aria-hidden="true" /><span>{label}</span></a>)}</div>
            </section>
            <button type="button" className="account-logout" onClick={() => { closeMenu(); logout(); }} data-testid="menu-logout"><LogOut size={17} aria-hidden="true" /> Log out</button>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </div>
  );
}
