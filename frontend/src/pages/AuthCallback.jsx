import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "@/lib/AuthContext";

export default function AuthCallback() {
  const { user, loading } = useAuth();
  const navigate = useNavigate();

  useEffect(() => {
    if (!loading) {
      navigate(user ? "/studio" : "/", { replace: true });
    }
  }, [user, loading, navigate]);

  return <div className="empty-state">Signing you in…</div>;
}
