import { useNavigate } from "react-router-dom";

export default function CheckoutCancel() {
  const nav = useNavigate();
  return (
    <div className="workspace" style={{ gridTemplateColumns: "1fr" }} data-testid="checkout-cancel">
      <div className="panel" style={{ maxWidth: 540, margin: "40px auto", textAlign: "center" }}>
        <h2>Checkout Canceled</h2>
        <p className="text-muted">No worries — your credits are unchanged.</p>
        <button className="btn-primary" onClick={() => nav("/credits")} data-testid="back-to-credits-btn">Back to Packs</button>
      </div>
    </div>
  );
}
