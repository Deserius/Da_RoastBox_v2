import { useEffect, useId, useLayoutEffect, useRef, useState } from "react";
import * as Dialog from "@radix-ui/react-dialog";
import { ArrowLeft, ArrowRight, BookOpen, Headphones, Pause, Play, RotateCcw, Volume2, X } from "lucide-react";
import { AUTHOR_CHAPTERS, AUTHOR_COVER_ART } from "../data/authorStory";
import { watchNarration } from "../lib/audioFocus";
import "../styles/about-author.css";

const TOTAL = AUTHOR_CHAPTERS.length;

// A lightweight approximation when an audio provider supplies no word timings.
// The full captions remain visible even if narration is unavailable.
function spokenSentence(sentences, currentTime, duration) {
  if (!duration || !currentTime) return 0;
  const weights = sentences.map((sentence) => Math.max(sentence.length, 1));
  const position = Math.min(currentTime / duration, 0.9999) * weights.reduce((a, b) => a + b, 0);
  let boundary = 0;
  return Math.max(0, weights.findIndex((weight) => { boundary += weight; return position < boundary; }));
}

export default function AboutAuthor({ className = "", testId = "about-author-trigger" }) {
  const [open, setOpen] = useState(false);
  // Zero is the cover; pages one through ten are chapters.
  const [page, setPage] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolume] = useState(0.85);
  const [autoAdvance, setAutoAdvance] = useState(false);
  const [audioError, setAudioError] = useState("");
  const audioRef = useRef(null);
  const bookRef = useRef(null);
  const autoRef = useRef(autoAdvance);
  const volumeRef = useRef(volume);
  const autoplayPage = useRef(null);
  const volumeId = useId();
  const chapter = page ? AUTHOR_CHAPTERS[page - 1] : null;

  // The cover and chapters have different heights. Always reveal the beginning
  // of a new page rather than inheriting the previous page's scroll position.
  useLayoutEffect(() => {
    if (open && bookRef.current) bookRef.current.scrollTop = 0;
  }, [open, page]);
  useEffect(() => { autoRef.current = autoAdvance; }, [autoAdvance]);
  useEffect(() => {
    volumeRef.current = volume;
    if (audioRef.current) audioRef.current.volume = volume;
  }, [volume]);

  useEffect(() => {
    if (!open || !chapter) return undefined;
    setPlaying(false);
    setCurrentTime(0);
    setDuration(0);
    setAudioError("");
    const audio = new Audio(chapter.audio);
    audio.preload = "metadata";
    audio.volume = volumeRef.current;
    audioRef.current = audio;
    const unwatchNarration = watchNarration(audio);
    const onPlay = () => { setPlaying(true); setAudioError(""); };
    const onPause = () => setPlaying(false);
    const onTime = () => setCurrentTime(Number.isFinite(audio.currentTime) ? audio.currentTime : 0);
    const onDuration = () => setDuration(Number.isFinite(audio.duration) ? audio.duration : 0);
    const onError = () => { setPlaying(false); setAudioError("Narration couldn't be loaded. You can still read the story, or try playing it again."); };
    const onEnded = () => {
      setPlaying(false);
      if (autoRef.current && page < TOTAL) {
        autoplayPage.current = page + 1;
        setPage(page + 1);
      }
    };
    const listeners = [["play", onPlay], ["pause", onPause], ["timeupdate", onTime],
      ["loadedmetadata", onDuration], ["durationchange", onDuration], ["error", onError], ["ended", onEnded]];
    listeners.forEach(([name, handler]) => audio.addEventListener(name, handler));
    if (autoplayPage.current === page) {
      autoplayPage.current = null;
      audio.play().catch(() => setAudioError("Your browser paused narration. Tap Play to continue."));
    }
    return () => {
      listeners.forEach(([name, handler]) => audio.removeEventListener(name, handler));
      audio.pause();
      unwatchNarration();
      audio.removeAttribute("src");
      audio.load();
      if (audioRef.current === audio) audioRef.current = null;
    };
  }, [open, page, chapter]);

  const goTo = (nextPage, withAudio = false) => {
    autoplayPage.current = withAudio && nextPage > 0 ? nextPage : null;
    if (audioRef.current) audioRef.current.pause();
    setPage(Math.min(TOTAL, Math.max(0, nextPage)));
  };
  const changePage = (nextPage) => goTo(nextPage, Boolean(audioRef.current && !audioRef.current.paused));
  const togglePlayback = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (!audio.paused) { audio.pause(); return; }
    if (audio.error) { audio.load(); }
    if (audio.ended) audio.currentTime = 0;
    setAudioError("");
    audio.play().catch(() => setAudioError("Your browser paused narration. Tap Play to try again."));
  };
  const replay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.error) audio.load();
    try { audio.currentTime = 0; } catch { /* The browser will begin at zero when metadata loads. */ }
    setAudioError("");
    audio.play().catch(() => setAudioError("Your browser paused narration. Tap Play to try again."));
  };
  const onOpenChange = (next) => {
    if (!next) {
      autoplayPage.current = null;
      audioRef.current?.pause();
      setPage(0);
      setAudioError("");
    }
    setOpen(next);
  };
  const activeSentence = chapter ? spokenSentence(chapter.sentences, currentTime, duration) : 0;

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Trigger asChild>
        <button type="button" className={`author-trigger ${className}`} data-testid={testId}>
          <BookOpen size={15} aria-hidden="true" /> About Developer
        </button>
      </Dialog.Trigger>
      <Dialog.Portal>
        <Dialog.Overlay className="author-overlay" data-testid="about-author-overlay">
          <Dialog.Content ref={bookRef} className="author-book" data-testid="about-author-dialog">
            <Dialog.Title className="author-sr-only">About Developer: Deserius Arte</Dialog.Title>
            <Dialog.Description className="author-sr-only">
              An illustrated, narrated ten-chapter story. Use the page controls to explore, or close to return to the app.
            </Dialog.Description>
            <header className="author-header">
              <span className="author-brand-mark" aria-hidden="true">D<span>.</span>A</span>
              <span className="author-header-title">THE STORY BEHIND THE BOX <span> / </span> DESERIUS ARTE</span>
              <Dialog.Close asChild>
                <button type="button" className="author-close" aria-label="Close About Developer" data-testid="author-close"><X size={21} aria-hidden="true" /></button>
              </Dialog.Close>
            </header>

            {page === 0 ? (
              <section className="author-cover author-turn" key="cover" data-testid="author-cover">
                <div className="author-cover-art">
                  <img src={AUTHOR_COVER_ART} alt="An illustrated portrait of Deserius Arte" />
                  <div className="author-art-shade" aria-hidden="true" />
                  <span className="author-cover-stamp"><span>01—10</span><br />AN UNUSUAL<br />LIFE IN PAGES</span>
                </div>
                <div className="author-cover-copy">
                  <div className="author-kicker"><span /> A CREATOR'S STORY</div>
                  <p className="author-cover-intro">A story by</p>
                  <h2>Deserius<br /><em>Arte.</em></h2>
                  <p className="author-cover-subtitle">Artist. Builder. Occasional cosmic commuter.</p>
                  <p className="author-cover-description">A curious kid, a tattoo machine, a detour through another reality, and a suspicious number of squirrels. Pull up a chair.</p>
                  <div className="author-cover-actions">
                    <button type="button" className="author-primary" onClick={() => goTo(1)} data-testid="author-start-reading">Open the story <ArrowRight size={17} aria-hidden="true" /></button>
                    <button type="button" className="author-outline" onClick={() => { setAutoAdvance(true); autoRef.current = true; goTo(1, true); }} data-testid="author-listen-story"><Headphones size={17} aria-hidden="true" /> Listen from the beginning</button>
                  </div>
                  <p className="author-cover-credit">Da RoastBox was created by <strong>Deserius Arte</strong> under the <strong>Hustler Anomalies Enterprises LLC</strong> brand.</p>
                </div>
              </section>
            ) : (
              <section className="author-chapter author-turn" key={page} data-testid="author-chapter">
                <div className="author-chapter-art">
                  <img src={chapter.image} alt={chapter.alt} data-testid="author-chapter-image" />
                  <div className="author-art-shade" aria-hidden="true" />
                  <div className="author-image-label"><span>THE DESERIUS ARTE STORY</span><strong>{chapter.number}</strong></div>
                </div>
                <div className="author-chapter-copy">
                  <div className="author-kicker"><span /> CHAPTER {chapter.number} / {String(TOTAL).padStart(2, "0")}</div>
                  <p className="author-chapter-eyebrow">{chapter.eyebrow}</p>
                  <h2 data-testid="author-page-title">{chapter.title}</h2>
                  <div className="author-rule"><span /></div>
                  <p className="author-story-text" data-testid="author-story-text">
                    {chapter.sentences.map((sentence, index) => (
                      <span key={sentence} className={playing && activeSentence === index ? "author-sentence-active" : ""}>{sentence}{index < chapter.sentences.length - 1 ? " " : ""}</span>
                    ))}
                  </p>
                  {page === TOTAL && <p className="author-last-word">WITH GRATITUDE &amp; A LITTLE COSMIC CURIOSITY <span>✦</span></p>}
                  <div className="author-audio" aria-label="Narration controls">
                    <div className="author-audio-heading"><span><Headphones size={14} aria-hidden="true" /> NARRATION</span><span>{playing ? "PLAYING" : "PRESS PLAY"}</span></div>
                    <div className="author-audio-progress" aria-hidden="true"><span style={{ width: `${duration ? Math.min(100, currentTime / duration * 100) : 0}%` }} /></div>
                    <div className="author-audio-controls">
                      <button type="button" className="author-play" onClick={togglePlayback} data-testid="author-play" aria-label={playing ? "Pause narration" : "Play narration"}>
                        {playing ? <Pause size={15} fill="currentColor" aria-hidden="true" /> : <Play size={15} fill="currentColor" aria-hidden="true" />}{playing ? "Pause" : currentTime > 0 && currentTime < duration ? "Resume" : "Play"}
                      </button>
                      <button type="button" className="author-replay" onClick={replay} data-testid="author-replay" aria-label="Replay this chapter's narration"><RotateCcw size={15} aria-hidden="true" /> Replay</button>
                      <div className="author-volume"><Volume2 size={16} aria-hidden="true" /><label htmlFor={volumeId} className="author-sr-only">Narration volume</label><input id={volumeId} type="range" min="0" max="1" step="0.05" value={volume} onChange={(event) => setVolume(Number(event.target.value))} /></div>
                    </div>
                    <label className="author-auto"><input type="checkbox" checked={autoAdvance} onChange={(event) => setAutoAdvance(event.target.checked)} data-testid="author-auto-advance" /> Continue to the next chapter after narration</label>
                    <p className="author-caption-note">Words highlight approximately as narration plays.</p>
                    {audioError && <p className="author-audio-error" role="status" data-testid="author-audio-error">{audioError}</p>}
                  </div>
                </div>
              </section>
            )}

            <footer className="author-footer">
              <div className="author-progress-block">
                <span className="author-progress-label">{page === 0 ? "THE COVER" : `PAGE ${String(page).padStart(2, "0")} OF ${String(TOTAL).padStart(2, "0")}`}</span>
                <progress max={TOTAL} value={page} aria-label={`Story progress: ${page} of ${TOTAL} chapters`} />
              </div>
              <div className="author-page-controls">
                {page > 0 && <button type="button" className="author-cover-link" onClick={() => goTo(0)} data-testid="author-cover-btn">Cover</button>}
                <button type="button" className="author-page-arrow" onClick={() => changePage(page - 1)} disabled={page === 0} aria-label="Previous page" data-testid="author-previous"><ArrowLeft size={18} aria-hidden="true" /></button>
                <button type="button" className="author-page-next" onClick={() => changePage(page + 1)} disabled={page === TOTAL} data-testid="author-next">{page === TOTAL ? "The end" : "Next"} <ArrowRight size={17} aria-hidden="true" /></button>
              </div>
            </footer>
          </Dialog.Content>
        </Dialog.Overlay>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
