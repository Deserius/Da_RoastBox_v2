// One small audio-focus bus for narration, previews, shows, and video. Owners
// are unique objects so one source cannot release another source's focus.
const owners = new Set();
const listeners = new Set();
const notify = () => listeners.forEach((listener) => listener(owners.size > 0));
export function claimAudioFocus(owner) { owners.add(owner); notify(); }
export function releaseAudioFocus(owner) { owners.delete(owner); notify(); }
export function subscribeAudioFocus(listener) {
  listeners.add(listener); listener(owners.size > 0);
  return () => listeners.delete(listener);
}
export function watchNarration(audio) {
  const owner = {};
  const claim = () => claimAudioFocus(owner);
  const release = () => releaseAudioFocus(owner);
  audio.addEventListener("play", claim);
  ["pause", "ended", "error"].forEach((event) => audio.addEventListener(event, release));
  return () => {
    audio.removeEventListener("play", claim);
    ["pause", "ended", "error"].forEach((event) => audio.removeEventListener(event, release));
    release();
  };
}
