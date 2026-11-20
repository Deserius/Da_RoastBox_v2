import { act } from "react";
import { createRoot } from "react-dom/client";
import { useShowDraft } from "./useShowDraft";
import { activateShowDrafts, clearShowDrafts, readShowDraft, writeShowDraft } from "../lib/showDraft";

let root, container, revoke;
function Form({ page }) {
  const [name, setName] = useShowDraft("studio.name", "");
  const [duration, setDuration] = useShowDraft("shared.duration", 3);
  const [photos, setPhotos] = useShowDraft("studio.images", [], { memoryOnly: true });
  return page === "studio" ? <>
    <button data-testid="edit" onClick={() => { setName("My guest"); setDuration(7); setPhotos([{ file: new File(["x"], "guest.png"), previewUrl: "blob:guest" }]); }}>edit</button>
    <div data-testid="value">{name}/{duration}/{photos[0]?.file.name || "none"}</div>
  </> : <div>Settings</div>;
}

beforeEach(() => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  sessionStorage.clear(); localStorage.clear();
  revoke = URL.revokeObjectURL; URL.revokeObjectURL = jest.fn();
  clearShowDrafts(); activateShowDrafts("first-user");
  container = document.createElement("div"); document.body.appendChild(container); root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  clearShowDrafts(); URL.revokeObjectURL = revoke; container.remove();
  delete global.IS_REACT_ACT_ENVIRONMENT;
});

test("keeps draft text, slider and uploaded files when navigating away and back", async () => {
  await act(async () => root.render(<Form page="studio" />));
  await act(async () => container.querySelector('[data-testid="edit"]').click());
  // Unmount the page component like a route transition, then mount it again.
  await act(async () => root.render(<div>Settings</div>));
  expect(URL.revokeObjectURL).not.toHaveBeenCalled();
  await act(async () => root.render(<Form page="studio" />));
  expect(container.querySelector('[data-testid="value"]').textContent).toBe("My guest/7/guest.png");
  expect(sessionStorage.getItem("roastbox_show_draft_v1:studio.name")).toContain("My guest");
  expect(sessionStorage.getItem("roastbox_show_draft_v1:studio.images")).toBeNull();
});

test("logout or switching accounts clears drafts and releases photo URLs", async () => {
  writeShowDraft("studio.images", [{ previewUrl: "blob:guest", file: {} }], true);
  writeShowDraft("studio.name", "Private guest");
  activateShowDrafts("second-user");
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:guest");
  expect(readShowDraft("studio.name", "")).toBe("");
  expect(sessionStorage.getItem("roastbox_show_draft_v1:studio.name")).toBeNull();
  writeShowDraft("studio.name", "Other guest");
  clearShowDrafts();
  writeShowDraft("studio.name", "late callback");
  expect(readShowDraft("studio.name", "")).toBe("");
});
