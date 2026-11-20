export default function ApiLoadError({ children = "The app couldn't load this information.", onRetry }) {
  return (
    <div role="alert" className="panel" data-testid="api-load-error" style={{ margin: "12px 0", fontSize: 13 }}>
      <span>{children} Check the connection and try again.</span>{" "}
      <button type="button" className="btn-secondary" onClick={onRetry}>Retry</button>
    </div>
  );
}
