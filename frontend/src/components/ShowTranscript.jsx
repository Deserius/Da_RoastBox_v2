const REACTION_ICON = { ooh: "😮 ooh", groan: "😬 groan", cheer: "🙌 cheer" };

export const ShowTranscript = ({ transcript, personaById, activeIdx, emptyText }) => {
  if (!transcript.length) return emptyText ? <div className="empty-state">{emptyText}</div> : null;
  return (
    <details className="transcript-disclosure" data-testid="transcript-disclosure">
      <summary>View full transcript</summary>
      <div className="transcript" data-testid="transcript">
        {transcript.map((line, i) => {
          const p = personaById[line.persona_id] || {};
          const t = line.type || "joke";
          const reaction = REACTION_ICON[line.reaction];
          return (
            <div key={i} className={`transcript-line ${activeIdx === i ? "active" : ""} line-${t}`} data-testid={`transcript-line-${i}`}>
              <img className="avatar" src={`/${p.image || ""}`} alt={p.name || ""} />
              <div className="body">
                <div className="name">
                  {p.displayName || p.name}
                  <span className={`beat-tag tag-${t}`} data-testid={`beat-tag-${i}`}>{t.replace("_", " ").toUpperCase()}</span>
                  {line.emotion && <span className="emotion-tag" data-testid={`emotion-tag-${i}`}>{line.emotion.replace("_", " ")}</span>}
                  {line.laugh_after && line.laugh_after !== "none" && (
                    <span className="laugh-tag" data-testid={`laugh-tag-${i}`}>{reaction || "😂"} {line.laugh_after}</span>
                  )}
                </div>
                <div className="text">{line.text}</div>
              </div>
            </div>
          );
        })}
      </div>
    </details>
  );
};
