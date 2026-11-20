// Short-lived show drafts, scoped to this browser tab and authenticated user.
// Text/options survive route changes and reloads via sessionStorage. File objects
// and their object URLs stay in memory only: browsers cannot safely restore a
// file input from storage, and we don't write guest photos to persistent disk.
const PREFIX = "roastbox_show_draft_v1:";
const OWNER = `${PREFIX}owner`;
let owner = null;
const memory = new Map();

function storage() {
  try { return window.sessionStorage; } catch { return null; }
}

export function clearShowDrafts() {
  const images = memory.get("studio.images");
  if (Array.isArray(images)) images.forEach(({ previewUrl }) => {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
  });
  memory.clear();
  owner = null;
  try {
    const store = storage();
    if (store) {
      for (let i = store.length - 1; i >= 0; i -= 1) {
        const key = store.key(i);
        if (key?.startsWith(PREFIX)) store.removeItem(key);
      }
    }
    // Remove settings the old studio stored indefinitely across logouts.
    ["rb_duration", "rb_heat", "rb_adult", "rb_crowd_volume"].forEach((key) => window.localStorage.removeItem(key));
  } catch { /* Storage may be unavailable; in-memory drafts still work. */ }
}

export function activateShowDrafts(userId) {
  if (!userId) { clearShowDrafts(); return; }
  let storedOwner = null;
  try { storedOwner = storage()?.getItem(OWNER) || null; } catch { /* no storage */ }
  if ((owner && owner !== userId) || (storedOwner && storedOwner !== userId)) clearShowDrafts();
  owner = userId;
  try { storage()?.setItem(OWNER, userId); } catch { /* use memory */ }
}

export function readShowDraft(key, initial, memoryOnly = false) {
  if (memory.has(key)) return memory.get(key);
  if (!memoryOnly && owner) {
    try {
      const raw = storage()?.getItem(PREFIX + key);
      if (raw != null) {
        const value = JSON.parse(raw);
        memory.set(key, value);
        return value;
      }
    } catch { /* bad value / storage unavailable */ }
  }
  return initial;
}

export function writeShowDraft(key, value, memoryOnly = false) {
  if (!owner) return; // A late callback after logout cannot recreate a draft.
  memory.set(key, value);
  if (!memoryOnly) {
    try { storage()?.setItem(PREFIX + key, JSON.stringify(value)); } catch { /* in-memory fallback */ }
  }
}
