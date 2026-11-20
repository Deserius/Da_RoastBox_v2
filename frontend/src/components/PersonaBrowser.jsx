import { useEffect, useId, useMemo, useRef, useState } from "react";
import { Info, Search, SlidersHorizontal, Star, X } from "lucide-react";
import { PersonaFavoriteButton } from "@/components/PersonaFavoriteButton";
import { PersonaProfileDialog } from "@/components/PersonaProfileDialog";
import { usePersonaFavorites } from "@/lib/PersonaFavoritesContext";

const TABS = [
  { id: "all", label: "All roasters" },
  { id: "free", label: "Free" },
  { id: "premium", label: "Premium" },
  { id: "favorites", label: "Favorites" },
];

const PersonaCard = ({ p, index, selected, mode, onPrimary, onInfo }) => {
  const name = p.displayName || p.name;
  const slot = mode === "battle" ? (index === 0 ? "A" : "B") : index + 1;
  const primaryLabel = mode === "showcase" ? `View ${name}'s profile`
    : p.locked ? `Unlock ${name}`
      : `${selected ? "Remove" : "Select"} ${name}${selected ? " from the lineup" : " for the lineup"}`;
  const testPrefix = mode === "showcase" ? "roaster-card" : mode === "battle" ? "battle-persona" : "persona-card";
  return (
    <article className={`persona-card ${selected ? "selected" : ""} ${p.locked ? "locked" : ""} ${p.is_premium ? "premium" : ""}`}
      data-testid={`${testPrefix}-${p.id}`}>
      <button type="button" className="persona-card-main" onClick={(event) => onPrimary(p, event)}
        aria-label={primaryLabel} aria-pressed={mode === "showcase" ? undefined : selected}>
        <span className="persona-portrait-wrap">
          <img src={`/${p.image}`} alt="" loading="lazy" decoding="async" />
          {selected && <span className="badge-num" aria-hidden="true">{slot}</span>}
          {p.is_premium && <span className="badge-premium" data-testid={`premium-badge-${p.id}`}>{p.locked ? "🔒 PREMIUM" : "PREMIUM · +5"}</span>}
        </span>
        <span className="name">{name}</span>
        <span className="tagline">{mode === "showcase" || mode === "battle" ? p.role : p.tagline}</span>
        {mode === "studio" && p.comic_inspiration && <span className="comic-inspo">~ {p.comic_inspiration}</span>}
      </button>
      <div className="persona-card-actions">
        <PersonaFavoriteButton persona={p} />
        <button type="button" className="persona-icon-action persona-info-action" onClick={(event) => onInfo(p, event)}
          aria-label={`About ${name}`} title={`About ${name}`} data-testid={`persona-info-${p.id}`}>
          <Info aria-hidden="true" size={18} strokeWidth={2} />
        </button>
      </div>
    </article>
  );
};

export const PersonaBrowser = ({ personas, selected = [], onSelect, onRandom, max = 5, mode = "studio" }) => {
  const [tab, setTab] = useState("all");
  const [search, setSearch] = useState("");
  const [access, setAccess] = useState("all");
  const [sort, setSort] = useState("featured");
  const [open, setOpen] = useState(null);
  const [expandedMobile, setExpandedMobile] = useState(false);
  useEffect(() => { setExpandedMobile(false); }, [tab, search, access, sort]);
  const browserId = useId();
  const lastTrigger = useRef(null);
  const tabRefs = useRef({});
  const { favoriteSet, status, retry } = usePersonaFavorites();
  const counts = useMemo(() => ({
    all: personas.length,
    free: personas.filter((p) => !p.is_premium).length,
    premium: personas.filter((p) => p.is_premium).length,
    favorites: personas.filter((p) => favoriteSet.has(p.id)).length,
  }), [personas, favoriteSet]);
  const shown = useMemo(() => {
    const query = search.trim().toLocaleLowerCase();
    const filtered = personas.filter((p) => {
      if (tab === "free" && p.is_premium) return false;
      if (tab === "premium" && !p.is_premium) return false;
      if (tab === "favorites" && !favoriteSet.has(p.id)) return false;
      if (access === "unlocked" && p.locked) return false;
      if (access === "locked" && !p.locked) return false;
      if (access.startsWith("gender:") && p.gender !== access.slice(7)) return false;
      if (!query) return true;
      const haystack = [p.displayName, p.name, p.role, p.tagline, p.description, p.comic_inspiration,
        ...(p.topics || []), ...(p.lingo || [])].filter(Boolean).join(" ").toLocaleLowerCase();
      return haystack.includes(query);
    });
    if (sort === "name") return [...filtered].sort((a, b) => (a.displayName || a.name).localeCompare(b.displayName || b.name));
    if (sort === "rating") return [...filtered].sort((a, b) => (b.rating || 0) - (a.rating || 0));
    return filtered;
  }, [personas, tab, search, access, sort, favoriteSet]);

  const openProfile = (p, event) => { lastTrigger.current = event.currentTarget; setOpen(p); };
  const primary = (p, event) => { if (mode === "showcase") openProfile(p, event); else onSelect(p); };
  const choose = (p) => { setOpen(null); onSelect(p); };
  const reset = () => { setTab("all"); setSearch(""); setAccess("all"); setSort("featured"); };
  const onTabKey = (event, id) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const current = TABS.findIndex((item) => item.id === id);
    const next = event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1
      : (current + (event.key === "ArrowRight" ? 1 : -1) + TABS.length) % TABS.length;
    setTab(TABS[next].id);
    tabRefs.current[TABS[next].id]?.focus();
  };
  const pickLabel = open?.locked ? "Unlock premium" : mode === "showcase" ? "Roast with them"
    : selected.includes(open?.id) ? (mode === "battle" ? "Remove fighter" : "Remove from lineup")
      : (mode === "battle" ? "Add to battle" : "Add to lineup");

  return (
    <div className="persona-browser" data-testid="persona-browser">
      {mode !== "showcase" && <div className="roster-toolbar">
        <span className="text-muted" style={{ fontSize: 12 }}>
          {selected.length}/{max} picked{mode === "studio" && <> · premium roasters add <strong>+5 credits</strong></>}
        </span>
        {onRandom && <button type="button" className="btn-secondary" onClick={onRandom} data-testid="randomize-personas-btn">🎲 Random lineup</button>}
      </div>}
      <div className="persona-tabs" role="tablist" aria-label="Roaster categories">
        {TABS.map((item) => <button key={item.id} ref={(node) => { tabRefs.current[item.id] = node; }} type="button" role="tab"
          id={`${browserId}-tab-${item.id}`} aria-controls={`${browserId}-panel`}
          className={`persona-tab ${tab === item.id ? "active" : ""}`} aria-selected={tab === item.id} tabIndex={tab === item.id ? 0 : -1}
          onClick={() => setTab(item.id)} onKeyDown={(event) => onTabKey(event, item.id)} data-testid={`persona-tab-${item.id}`}>
          {item.id === "favorites" && <Star size={14} aria-hidden="true" />}<span>{item.label}</span>
          <small>{item.id === "favorites" && status !== "ready" ? "–" : counts[item.id]}</small>
        </button>)}
      </div>
      <div className="persona-tools">
        <label className="persona-search">
          <Search size={18} aria-hidden="true" />
          <input type="search" value={search} onChange={(event) => setSearch(event.target.value)}
            placeholder="Search names, styles or topics..." aria-label="Search roasters" data-testid="persona-search" />
          {search && <button type="button" onClick={() => setSearch("")} aria-label="Clear search"><X size={16} /></button>}
        </label>
        <label className="persona-select-wrap">
          <SlidersHorizontal size={15} aria-hidden="true" />
          <select value={access} onChange={(event) => setAccess(event.target.value)} aria-label="Filter roasters" data-testid="persona-access-filter">
            <option value="all">All filters</option>
            <optgroup label="Access"><option value="unlocked">Available</option><option value="locked">Locked</option></optgroup>
            <optgroup label="Persona gender"><option value="gender:female">Female personas</option><option value="gender:male">Male personas</option><option value="gender:other">Other personas</option></optgroup>
          </select>
        </label>
        <label className="persona-select-wrap sort">
          <span>Sort</span>
          <select value={sort} onChange={(event) => setSort(event.target.value)} aria-label="Sort roasters" data-testid="persona-sort">
            <option value="featured">Featured</option><option value="name">Name A–Z</option><option value="rating">Highest rated</option>
          </select>
        </label>
      </div>
      {status === "error" && <div className="persona-favorites-error" role="alert">Couldn't load your favorites. <button type="button" onClick={retry}>Retry</button></div>}
      <div className="persona-results-count" aria-live="polite">{shown.length} {shown.length === 1 ? "roaster" : "roasters"}</div>
      <div role="tabpanel" id={`${browserId}-panel`} aria-labelledby={`${browserId}-tab-${tab}`}>
        {shown.length ? <>
          <div className={`persona-grid ${mode === "showcase" ? "showcase" : ""} ${expandedMobile ? "persona-mobile-expanded" : ""}`} data-testid={mode === "showcase" ? "roaster-grid" : "persona-grid"}>
            {shown.map((p) => <PersonaCard key={p.id} p={p} index={selected.indexOf(p.id)} selected={selected.includes(p.id)}
              mode={mode} onPrimary={primary} onInfo={openProfile} />)}
          </div>
          {shown.length > 8 && <button type="button" className="btn-secondary persona-mobile-expand" aria-expanded={expandedMobile}
            onClick={() => setExpandedMobile((value) => !value)} data-testid="persona-mobile-expand">
            {expandedMobile ? "Show fewer roasters" : `Show all ${shown.length} roasters`}
          </button>}
        </> : <div className="persona-empty" data-testid="persona-empty">
          <Star size={24} aria-hidden="true" />
          <strong>{tab === "favorites" && status === "loading" ? "Loading favorites…" : tab === "favorites" && !favoriteSet.size && !search ? "No favorites yet" : "No roasters found"}</strong>
          <span>{tab === "favorites" && !favoriteSet.size && !search ? "Tap the outline star on a card to save a favorite." : "Try a different search or filter."}</span>
          <button type="button" className="btn-ghost" onClick={reset}>See all roasters</button>
        </div>}
      </div>
      {open && <PersonaProfileDialog persona={open} onClose={() => setOpen(null)} onPick={choose} pickLabel={pickLabel} returnFocus={lastTrigger} />}
    </div>
  );
};
