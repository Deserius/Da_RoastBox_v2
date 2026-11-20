export const HotSeatForm = ({ subjectName, setSubjectName, contextText, setContextText, offLimits, setOffLimits, images, onPick, onRemove, max }) => {
  return (
    <>
      <div className="hotseat-grid">
        <label className={`upload-zone compact ${images.length >= max ? "upload-disabled" : ""}`} data-testid="upload-zone">
          <input type="file" className="file-input-visually-hidden" accept="image/jpeg,image/png,image/webp" multiple
            disabled={images.length >= max} onChange={onPick} aria-label="Add photos" data-testid="image-file-input" />
          <span className="icon" aria-hidden="true">📸</span>
          <span>{images.length >= max ? "Maximum photos added" : "Add photos"} ({images.length}/{max})</span>
          <span className="hint">JPEG, PNG or WebP · up to 8 MB each</span>
        </label>
        {images.map((im, idx) => (
          <div key={im.previewUrl} className="image-preview">
            <img src={im.previewUrl} alt="" />
            <button type="button" onClick={() => onRemove(idx)} aria-label={`Remove photo ${idx + 1}`} data-testid={`remove-image-${idx}`}>×</button>
          </div>
        ))}
      </div>
      <p className="hotseat-input-hint">Your setup stays while you navigate. For privacy, photos need to be reselected after a page refresh.</p>
      <label className="label" htmlFor="hotseat-name">Their name or nickname</label>
      <input id="hotseat-name" className="input" maxLength={120} placeholder="e.g. Marcus" value={subjectName} onChange={(e) => setSubjectName(e.target.value)} data-testid="subject-name-input" />
      <label className="label" htmlFor="hotseat-ammo" style={{ marginTop: 10 }}>Personal ammo — the details that make it hit</label>
      <textarea id="hotseat-ammo" className="textarea" maxLength={3000} placeholder="A hobby, harmless bad habit, legendary fail, inside joke, or story the comics can call back to…" value={contextText}
        onChange={(e) => setContextText(e.target.value)} data-testid="context-textarea" aria-describedby="ammo-hint" />
      <p className="hotseat-input-hint" id="ammo-hint">Specific stories and quirks give the comics more to work with. Skip sensitive details.</p>
      <p className="hotseat-input-hint">A fallback writer may receive your name, context, boundaries, and photo observations (not photos), and may cache responses. Skip sensitive details.</p>
      <label className="label" htmlFor="hotseat-boundaries" style={{ marginTop: 10 }}>Off-limits topics <span className="hotseat-optional">optional</span></label>
      <input id="hotseat-boundaries" className="input" maxLength={600} placeholder="Anything the writers should leave out" value={offLimits}
        onChange={(e) => setOffLimits(e.target.value)} data-testid="off-limits-input" aria-describedby="boundaries-hint" />
      <p className="hotseat-input-hint" id="boundaries-hint">We'll ask the writer to avoid these topics; review generated content before sharing.</p>
    </>
  );
};
