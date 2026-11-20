import { Star } from "lucide-react";
import { usePersonaFavorites } from "@/lib/PersonaFavoritesContext";

export const PersonaFavoriteButton = ({ persona, inModal = false }) => {
  const { favoriteSet, pendingSet, status, toggle } = usePersonaFavorites();
  const favorite = favoriteSet.has(persona.id);
  const name = persona.displayName || persona.name || "roaster";
  const label = `${favorite ? "Remove" : "Add"} ${name} ${favorite ? "from" : "to"} favorites`;
  return (
    <button type="button" className={`${inModal ? "persona-favorite-wide" : "persona-icon-action"} ${favorite ? "is-favorite" : ""}`}
      aria-label={label} aria-pressed={favorite} title={status === "loading" ? "Loading favorites…" : label}
      disabled={status !== "ready" || pendingSet.has(persona.id)}
      onClick={(e) => { e.stopPropagation(); toggle(persona.id); }}
      data-testid={`${inModal ? "persona-modal-favorite" : "persona-favorite"}-${persona.id}`}>
      <Star aria-hidden="true" size={inModal ? 16 : 17} strokeWidth={2} fill={favorite ? "currentColor" : "none"} />
      {inModal && <span>{favorite ? "Favorited" : "Add to favorites"}</span>}
    </button>
  );
};
