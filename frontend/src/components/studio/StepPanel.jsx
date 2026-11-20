export const StepPanel = ({ n, title, hint, done, children, testid, right }) => (
  <div className={`panel step-panel ${done ? "done" : ""}`} id={testid} data-testid={testid}>
    <div className="step-head">
      <span className="step-num">{n}</span>
      <div className="step-title-wrap">
        <h2 className="step-title">{title}</h2>
        {hint && <div className="step-hint">{hint}</div>}
      </div>
      {right}
    </div>
    {children}
  </div>
);

export const Stepper = ({ steps }) => (
  <nav className="stepper" aria-label="Jump to a studio step" data-testid="studio-stepper">
    <span className="stepper-help">Jump to a step</span>
    {steps.map((s, i) => (
      <button key={s.label} type="button" className={`stepper-item ${s.done ? "done" : ""}`}
        onClick={() => document.getElementById(s.target)?.scrollIntoView({
          behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "start",
        })} data-testid={`studio-jump-${s.target}`}>
        <span className="stepper-dot" aria-hidden="true">{i + 1}</span>
        <span className="stepper-label">{s.label}</span>
        {i < steps.length - 1 && <span className="stepper-line" aria-hidden="true" />}
      </button>
    ))}
  </nav>
);
