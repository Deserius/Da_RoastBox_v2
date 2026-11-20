import { useCallback, useEffect, useRef, useState } from "react";
import { mediaObjectUrl } from "@/lib/media";
import { crowd } from "@/lib/crowdEngine";
import { claimAudioFocus, releaseAudioFocus } from "@/lib/audioFocus";

const wait = (ms, run) => new Promise((resolve) => {
  if (run.stopped) { resolve(); return; }
  const finish = () => {
    clearTimeout(id);
    run.abort.signal.removeEventListener("abort", finish);
    resolve();
  };
  const id = setTimeout(finish, ms);
  run.timers.push(id);
  run.abort.signal.addEventListener("abort", finish, { once: true });
});

const loadVoice = async (beat, run) => {
  if (!beat?.audio_url) return null;
  try {
    const url = await mediaObjectUrl(beat.audio_url, run.abort.signal);
    if (run.stopped) { URL.revokeObjectURL(url); return null; }
    run.urls.add(url);
    const audio = new Audio(url);
    audio.preload = "auto";
    return { audio, url };
  } catch {
    return run.stopped ? null : { error: true };
  }
};

const speak = (audio, beat, index, run, onMediaError, onBlocked, onUnblocked) => new Promise((resolve) => {
  const words = (beat.text || "").trim().split(/\s+/).filter(Boolean).length;
  const fallbackMs = Math.max(1200, Math.min(12000, words * 320));
  let finished = false;
  let fallingBack = false;
  const done = () => {
    if (finished) return;
    finished = true;
    run.retrySpeech = null;
    run.skipSpeech = null;
    if (run.speech?.index === index) run.speech.finished = true;
    resolve();
  };
  const fallback = (reportError) => {
    if (finished || fallingBack || run.stopped) return;
    fallingBack = true;
    run.retrySpeech = null;
    run.skipSpeech = null;
    onUnblocked?.();
    if (reportError) onMediaError?.();
    run.audio = null;
    run.speech = { index, audio: null, startedAt: performance.now(), durationMs: fallbackMs, finished: false };
    wait(fallbackMs, run).then(done);
  };
  run.resolveSpeech = done;
  if (!audio) { fallback(false); return; }
  run.audio = audio;
  run.speech = { index, audio, startedAt: null, durationMs: fallbackMs, finished: false };
  audio.onplaying = () => {
    if (run.speech?.index === index) run.speech.startedAt = performance.now();
    onUnblocked?.();
  };
  audio.onended = done;
  audio.onerror = () => fallback(true);
  const attempt = () => {
    if (finished || run.stopped) return;
    run.retrySpeech = null;
    // Must be called directly from the retry button's user gesture.
    let result;
    try { result = audio.play(); }
    catch (error) { result = Promise.reject(error); }
    Promise.resolve(result).then(() => {
      if (run.stopped || finished) return;
      onUnblocked?.();
      if (run.speech?.index === index && run.speech.startedAt === null) run.speech.startedAt = performance.now();
    }).catch((error) => {
      if (finished || run.stopped) return;
      if (error?.name === "NotAllowedError") {
        run.retrySpeech = attempt;
        run.skipSpeech = () => fallback(false);
        onBlocked?.();
      } else fallback(true);
    });
  };
  attempt();
});

/** Plays a show: room tone → intro cheer → beats with comedic pauses, layered crowd reactions, tags riding the laugh. */
export function useShowPlayer({ onBeatDone, onFinish, onReaction, onMediaError } = {}) {
  const [activeIdx, setActiveIdx] = useState(-1);
  const [playing, setPlaying] = useState(false);
  const [needsAudioTap, setNeedsAudioTap] = useState(false);
  const runRef = useRef(null);
  const audioFocusOwner = useRef({});
  const cbRef = useRef({ onBeatDone, onFinish, onReaction, onMediaError });
  cbRef.current = { onBeatDone, onFinish, onReaction, onMediaError };
  const currentSpeech = useCallback(() => runRef.current?.speech || null, []);

  const stop = useCallback(() => {
    const run = runRef.current;
    if (run) {
      run.stopped = true;
      run.timers.forEach(clearTimeout);
      run.audio?.pause();
      run.resolveSpeech?.();
      run.abort.abort();
      run.urls.forEach((url) => URL.revokeObjectURL(url));
      run.urls.clear();
    }
    runRef.current = null;
    crowd.stopAll();
    releaseAudioFocus(audioFocusOwner.current);
    setActiveIdx(-1);
    setPlaying(false);
    setNeedsAudioTap(false);
  }, []);

  const resumeAudio = useCallback(() => {
    const run = runRef.current;
    if (!run || run.stopped || !run.retrySpeech) return;
    // Both the Web Audio context and the blocked voice are resumed by this tap.
    crowd.unlock();
    setNeedsAudioTap(false);
    run.retrySpeech();
  }, []);

  const useCaptionsOnly = useCallback(() => {
    const run = runRef.current;
    if (!run || run.stopped || !run.skipSpeech) return;
    run.captionsOnly = true;
    crowd.stopAll();
    setNeedsAudioTap(false);
    run.skipSpeech();
  }, []);

  const play = useCallback(async (lines, { introMs, onIntroStart, rapBattle = false } = {}) => {
    stop();
    if (!lines?.length) return;
    const run = { stopped: false, captionsOnly: false, retrySpeech: null, skipSpeech: null, timers: [], audio: null, speech: null, resolveSpeech: null, abort: new AbortController(), urls: new Set() };
    runRef.current = run;
    claimAudioFocus(audioFocusOwner.current);
    setPlaying(true);
    await crowd.unlock();
    if (run.stopped) return;
    onIntroStart?.();
    const cheer = crowd.intro();
    await wait(introMs ?? cheer, run);
    if (run.stopped) return;
    if (rapBattle) crowd.startBeat();
    const onVoiceError = () => cbRef.current.onMediaError?.();
    const voices = lines.map((b, i) => (i < 3 ? loadVoice(b, run) : null));
    for (let i = 0; i < lines.length; i++) {
      if (run.stopped) return;
      const beat = lines[i];
      if (i + 3 < lines.length && !run.captionsOnly) voices[i + 3] = loadVoice(lines[i + 3], run);
      // Never let the next caption read timing from the preceding voice clip.
      run.audio = null;
      run.speech = null;
      run.resolveSpeech = null;
      setActiveIdx(i);
      const isTag = beat.type === "tag";
      const before = isTag || beat.rapid_fire ? Math.min(180, beat.pause_before_ms || 0) : Math.min(1500, beat.pause_before_ms || 0);
      if (before) await wait(before, run);
      if (run.stopped) return;
      const voice = run.captionsOnly ? null : await voices[i];
      if (run.stopped) return;
      if (voice?.error) onVoiceError();
      // Wait for the voice to be ready, then duck the entire crowd bus before
      // playback. The bus also covers reactions scheduled during the line.
      if (!run.captionsOnly) {
        crowd.duck();
        await wait(70, run); // Give the short attack time to finish before the voice starts.
        if (run.stopped) return;
      }
      if (rapBattle && !run.captionsOnly) {
        await wait(crowd.msToBeat(), run);
        if (run.stopped) return;
      }
      await speak(voice?.audio, beat, i, run, onVoiceError,
        () => setNeedsAudioTap(true), () => setNeedsAudioTap(false));
      if (voice?.url) { URL.revokeObjectURL(voice.url); run.urls.delete(voice.url); }
      voices[i] = null;
      if (run.stopped) return;
      if (!run.captionsOnly) crowd.releaseDuck();
      cbRef.current.onBeatDone?.(beat, i);
      const nextIsTag = lines[i + 1]?.type === "tag" && lines[i + 1]?.persona_id === beat.persona_id;
      const rapidFire = !!(beat.rapid_fire && lines[i + 1]?.rapid_fire);
      const hold = run.captionsOnly ? 0 : crowd.react(beat.laugh_after || "none", beat.reaction || "laugh", { nextIsTag, rapidFire });
      cbRef.current.onReaction?.(beat, i);
      const breathe = Math.min(rapidFire ? 250 : 800, beat.pause_after_ms || 0);
      await wait(Math.max(hold, breathe) + (i === lines.length - 1 ? 0 : 120), run);
    }
    if (run.stopped) return;
    crowd.stopBeat();
    if (!run.captionsOnly) crowd.outro();
    setActiveIdx(-1);
    setPlaying(false);
    run.abort.abort();
    run.urls.forEach((url) => URL.revokeObjectURL(url));
    run.urls.clear();
    runRef.current = null;
    releaseAudioFocus(audioFocusOwner.current);
    cbRef.current.onFinish?.();
  }, [stop]);

  useEffect(() => () => stop(), [stop]);

  return { play, stop, activeIdx, playing, currentSpeech, needsAudioTap, resumeAudio, useCaptionsOnly };
}
