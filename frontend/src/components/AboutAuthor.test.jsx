import { act } from "react";
import { createRoot } from "react-dom/client";
import AboutAuthor from "./AboutAuthor";

// This is a control-flow test. Browser/device tests separately verify real MP3s
// and generated illustrations; no provider or paid service is contacted here.
class FakeAudio extends EventTarget {
  static instances = [];
  constructor(src) {
    super();
    this.src = src;
    this.currentTime = 0;
    this.duration = 20;
    this.paused = true;
    this.ended = false;
    this.volume = 1;
    this.error = null;
    FakeAudio.instances.push(this);
  }
  play() { this.paused = false; this.dispatchEvent(new Event("play")); return Promise.resolve(); }
  pause() { this.paused = true; this.dispatchEvent(new Event("pause")); }
  load() {}
  removeAttribute() {}
}

const byTestId = (id) => document.querySelector(`[data-testid="${id}"]`);
const click = async (id) => act(async () => { byTestId(id).click(); });

let originalAudio;
let container;
let root;
beforeEach(async () => {
  global.IS_REACT_ACT_ENVIRONMENT = true;
  originalAudio = global.Audio;
  global.Audio = FakeAudio;
  FakeAudio.instances = [];
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  await act(async () => root.render(<AboutAuthor />));
});
afterEach(async () => {
  await act(async () => root.unmount());
  container.remove();
  global.Audio = originalAudio;
  delete global.IS_REACT_ACT_ENVIRONMENT;
});

test("opens a cover, navigates chapters, controls audio, and returns to the app", async () => {
  await click("about-author-trigger");
  expect(byTestId("author-cover")).not.toBeNull();
  expect(document.body.textContent).toContain("Hustler Anomalies Enterprises LLC");
  await click("author-start-reading");
  expect(byTestId("author-page-title").textContent).toBe("The Kid Who Asked Why");
  expect(FakeAudio.instances.at(-1).src).toContain("audio/01.mp3");
  await click("author-play");
  expect(byTestId("author-play").textContent).toContain("Pause");
  await click("author-play");
  expect(byTestId("author-play").textContent).toContain("Play");
  FakeAudio.instances.at(-1).currentTime = 5;
  await click("author-replay");
  expect(FakeAudio.instances.at(-1).currentTime).toBe(0);
  await click("author-next");
  expect(byTestId("author-page-title").textContent).toBe("The QBasic Incident");
  expect(FakeAudio.instances.at(-1).src).toContain("audio/02.mp3");
  expect(FakeAudio.instances.at(-1).paused).toBe(false);
  await click("author-previous");
  expect(byTestId("author-page-title").textContent).toBe("The Kid Who Asked Why");
  await click("author-cover-btn");
  expect(byTestId("author-cover")).not.toBeNull();
  await click("author-close");
  expect(byTestId("about-author-dialog")).toBeNull();
});

test("narrated story advances after audio ends and displays the requested thanks", async () => {
  await click("about-author-trigger");
  await click("author-listen-story");
  expect(byTestId("author-auto-advance").checked).toBe(true);
  expect(FakeAudio.instances.at(-1).paused).toBe(false);
  for (let page = 1; page < 10; page += 1) {
    await act(async () => FakeAudio.instances.at(-1).dispatchEvent(new Event("ended")));
  }
  expect(byTestId("author-page-title").textContent).toBe("Rewriting Reality");
  const text = byTestId("author-story-text").textContent;
  expect(text.indexOf("God")).toBeLessThan(text.indexOf("mama"));
  expect(text.indexOf("mama")).toBeLessThan(text.indexOf("hold dear"));
  expect(text).toContain("AI solutions and ChatGPTs");
  expect(text).toContain("Deserius Arte");
  expect(text).toContain("Hustler Anomalies Enterprises LLC");
  expect(byTestId("author-next").disabled).toBe(true);
});
