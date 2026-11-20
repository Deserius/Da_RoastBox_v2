import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { useAuth } from "@/lib/AuthContext";
import ApiLoadError from "@/components/ApiLoadError";
import { PersonaBrowser } from "@/components/PersonaBrowser";

export default function RoastersPage() {
  const [personas, setPersonas] = useState([]);
  const [loadError, setLoadError] = useState(false);
  const [reload, setReload] = useState(0);
  const { user } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    let active = true;
    setLoadError(false);
    api.get("/personas").then(({ data }) => { if (active) setPersonas(data.personas || []); })
      .catch(() => { if (active) setLoadError(true); });
    return () => { active = false; };
  }, [user?.premium_personas_unlocked, user?.plan_tier, reload]);

  const pick = (p) => navigate(p.locked ? "/credits" : `/studio?persona=${encodeURIComponent(p.id)}`);
  return (
    <div className="page-wrap roasters-page" data-testid="roasters-page">
      <div className="page-head roasters-head">
        <span className="roasters-kicker">THE LINEUP <span>✦</span> DA ROASTBOX</span>
        <h1 className="page-title">Meet the Roasters<span className="roasters-dot">.</span></h1>
        <p className="page-sub">Find your kind of funny. Explore their bios, hear their voice and save your favorites.</p>
      </div>
      {loadError && <ApiLoadError onRetry={() => setReload((n) => n + 1)}>Couldn't load the roaster lineup.</ApiLoadError>}
      <PersonaBrowser personas={personas} onSelect={pick} mode="showcase" />
    </div>
  );
}
