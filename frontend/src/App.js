import { useState } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import "@/App.css";
import { AuthProvider, useAuth } from "@/lib/AuthContext";
import { ConsentProvider } from "@/lib/ConsentContext";
import { LoungeProvider } from "@/lib/LoungeContext";
import { ToastProvider } from "@/lib/ToastContext";
import { PersonaFavoritesProvider } from "@/lib/PersonaFavoritesContext";
import { ConsentGate } from "@/components/AdultConsent";
import CinematicIntro from "@/components/CinematicIntro";
import TopBar from "@/components/TopBar";
import SplashScreen from "@/pages/SplashScreen";
import RoastStudio from "@/pages/StudioPage";
import "@/styles/v8.css";
import "@/styles/personas.css";
import CreditsPage from "@/pages/CreditsPage";
import CheckoutSuccess from "@/pages/CheckoutSuccess";
import CheckoutCancel from "@/pages/CheckoutCancel";
import SettingsPage from "@/pages/SettingsPage";
import AuthCallback from "@/pages/AuthCallback";
import EmailTokenPage from "@/pages/EmailTokenPage";
import RoastersPage from "@/pages/RoastersPage";
import BattlePage from "@/pages/BattlePage";
import SharePage from "@/pages/SharePage";

function Landing({ active }) {
  return <SplashScreen active={active} />;
}

const Protected = ({ children, intro }) => {
  const { user, loading } = useAuth();
  if (intro) return null;
  if (loading) return <div className="empty-state">Loading…</div>;
  if (!user) return <Navigate to="/" replace />;
  return <ConsentGate>{children}</ConsentGate>;
};

const Shell = ({ children }) => (
  <div className="app-shell">
    <TopBar />
    {children}
    <footer className="footer">
      <span>Da RoastBox! © Hustler Anomalies Enterprises LLC · Created by Deserius Arte · 18+ Entertainment Only</span>
    </footer>
  </div>
);

function App() {
  // A new page load is a new launch; navigation within the app does not replay it.
  const [intro, setIntro] = useState(true);
  return (
    <AuthProvider>
      <ConsentProvider>
        <LoungeProvider>
          <ToastProvider>
            <PersonaFavoritesProvider>
              <div inert={intro ? true : undefined} style={{ display: "contents" }}>
              <BrowserRouter>
                <Routes>
                  <Route path="/" element={<Landing active={!intro} />} />
                  <Route path="/auth/callback" element={<AuthCallback />} />
                  <Route path="/auth/verify" element={<EmailTokenPage purpose="verify" />} />
                  <Route path="/auth/reset" element={<EmailTokenPage purpose="reset" />} />
                  <Route path="/studio" element={<Protected intro={intro}><Shell><RoastStudio /></Shell></Protected>} />
                  <Route path="/credits" element={<Protected intro={intro}><Shell><CreditsPage /></Shell></Protected>} />
                  <Route path="/credits/success" element={<Protected intro={intro}><Shell><CheckoutSuccess /></Shell></Protected>} />
                  <Route path="/credits/cancel" element={<Protected intro={intro}><Shell><CheckoutCancel /></Shell></Protected>} />
                  <Route path="/settings" element={<Protected intro={intro}><Shell><SettingsPage /></Shell></Protected>} />
                  <Route path="/roasters" element={<Protected intro={intro}><Shell><RoastersPage /></Shell></Protected>} />
                  <Route path="/battle" element={<Protected intro={intro}><Shell><BattlePage /></Shell></Protected>} />
                  <Route path="/r/:shareId" element={intro ? null : <ConsentGate><SharePage /></ConsentGate>} />
                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </BrowserRouter>
              </div>
              {intro && <CinematicIntro onDone={() => setIntro(false)} />}
            </PersonaFavoritesProvider>
          </ToastProvider>
        </LoungeProvider>
      </ConsentProvider>
    </AuthProvider>
  );
}

export default App;
