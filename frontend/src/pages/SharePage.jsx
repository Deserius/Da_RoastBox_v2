import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import api from "@/lib/api";
import { crowd } from "@/lib/crowdEngine";
import { ShowTranscript } from "@/components/ShowTranscript";
import { RoastTheater } from "@/components/theater/RoastTheater";

export default function SharePage() {
  const { shareId } = useParams();
  const [show, setShow] = useState(null);
  const [error, setError] = useState("");
  const [theater, setTheater] = useState(false);

  useEffect(() => {
    api.get(`/share/${shareId}`).then(({ data }) => setShow(data)).catch((e) => setError(e?.response?.data?.detail || "Roast not found"));
  }, [shareId]);

  const byId = useMemo(() => Object.fromEntries((show?.personas || []).map((p) => [p.id, p])), [show]);
  const winner = show?.battle && byId[show.battle.winner];

  return (
    <div className="app-shell" data-testid="share-page">
      <header className="topbar">
        <Link to="/" className="brand" data-testid="share-brand-link"><span className="brand-flame">🔥</span><span>DA ROASTBOX!</span></Link>
        <Link to="/" className="btn-primary" data-testid="share-cta-btn">Roast your friends</Link>
      </header>
      <div className="page-wrap">
        {error && <div className="empty-state" data-testid="share-error">{error}</div>}
        {show && (
          <div className="panel">
            <h1 className="page-title" data-testid="share-title">
              {show.mode === "battle" ? `🥊 ${show.personas.map((p) => p.displayName).join(" vs ")}` : `🔥 The Roast of ${show.subject_name || "Tonight's Victim"}`}
            </h1>
            {winner && <div className="winner-badge inline" data-testid="share-winner">🏆 {winner.displayName} won ({Object.values(show.battle.scores).join(" – ")})</div>}
            <div className="show-actions">
              <button className="btn-primary" onClick={() => { crowd.unlock(); setTheater(true); }} data-testid="share-play-btn">▶ Watch the show</button>
            </div>
            <ShowTranscript transcript={show.transcript} personaById={byId} activeIdx={-1} />
            <p className="disclaimer">18+ adult comedy. Made with Da RoastBox — AI roasters, real crowd energy.</p>
          </div>
        )}
        {theater && show && (
          <RoastTheater transcript={show.transcript} personaById={byId} images={show.images} subjectName={show.subject_name}
            lineupIds={show.personas.map((p) => p.id)} mode={show.mode} battleStyle={show.battle_style} battle={show.battle} onClose={() => setTheater(false)} />
        )}
      </div>
    </div>
  );
}
