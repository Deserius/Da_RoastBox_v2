#!/usr/bin/env python3
"""Offline-only mock coverage for optional two-stage writer; no network calls."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import services.roast_writer as w
from services.highlight_reel import _hold, build_timeline

people = [{"id": "p1", "name": "One"}, {"id": "p2", "name": "Two"}]
lines = [{"persona_id": f"p{1+i%2}", "type": "joke", "text": f"Original offline observation joke number {i}.", "laugh_after": "small"} for i in range(10)]
class Fake:
    def __init__(self, reply):
        self.calls = []
        self.reply = reply
        self.chat = SimpleNamespace(completions=self)
    def create(self, **kw):
        self.calls.append(kw)
        if isinstance(self.reply, Exception): raise self.reply
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.reply))])

async def main():
    vision = Fake(json.dumps({"photos": [{"image_index": 0, "details": ["red hat", "family portrait"]}]}))
    creative = Fake(json.dumps({"script": lines}))
    with patch.object(w, 'ROAST_WRITER_PROVIDER', 'openrouter'), patch.object(w, 'ROAST_WRITER_PROFILE', 'free'), patch.object(w, 'OPENROUTER_API_KEY', 'fake-only'), patch.object(w, 'EMERGENT_LLM_KEY', ''), patch.object(w, 'ROAST_WRITER_MODEL', 'test-model:free'), patch.object(w, 'ROAST_FREE_BACKUP_MODEL', ''), patch.object(w, 'ROAST_FREE_WRITER_ONLY', True), patch.object(w, 'ROAST_POLLINATIONS_FALLBACK', False), patch.object(w, 'ROAST_ALLOW_PAID_WRITER_FALLBACK', False), patch.object(w, 'get_client', return_value=vision), patch.object(w, '_creative_client', return_value=creative):
        result = await w.write_script('offline prompt', people, [b'private image bytes'], ['image/jpeg'], 'BYOK_PRIVATE', expected_beats=10, off_limits='family')
        assert len(result) == 10 and len(vision.calls) == len(creative.calls) == 1
        request = json.dumps(creative.calls)
        assert 'red hat' in request and 'family portrait' not in request
        assert 'data:image' not in request and 'private image bytes' not in request and 'BYOK_PRIVATE' not in request
        # BYOK vision respects the configured free/premium OpenAI model tier
        # (standard here, by default) rather than always hardcoding gpt-4o.
        assert vision.calls[0]['model'] == w.ROAST_OPENAI_FREE_MODEL and creative.calls[0]['model'] == 'test-model:free'
        creative.calls.clear(); vision.calls.clear()
        await w.write_script('text only', people, [], [], expected_beats=10)
        assert not vision.calls and len(creative.calls) == 1
        broken = Fake(RuntimeError('network failure'))
        with patch.object(w, '_creative_client', return_value=broken):
            try: await w.write_script('text only', people, [], [], expected_beats=10)
            except RuntimeError: pass
            else: raise AssertionError('failed writer must fail explicitly')
            assert len(broken.calls) == 1
        with patch.object(w, 'EMERGENT_LLM_KEY', 'fake-backup'), patch.object(w, 'ROAST_FREE_WRITER_ONLY', False), patch.object(w, 'ROAST_ALLOW_PAID_WRITER_FALLBACK', True), patch.object(w, '_creative_client', return_value=broken), patch.object(w, 'get_emergent_client', return_value=creative):
            creative.calls.clear(); broken.calls.clear()
            await w.write_script('text only', people, [], [], 'USER_BYOK', expected_beats=10)
            assert len(broken.calls) == len(creative.calls) == 1
            assert 'USER_BYOK' not in json.dumps(creative.calls)
        # Two free OpenRouter attempts, then an anonymous mocked POST; no credentials or photos.
        class AnonymousHTTP:
            calls = []
            def __init__(self, **kw): pass
            async def __aenter__(self): return self
            async def __aexit__(self, *args): pass
            async def post(self, url, json):
                self.calls.append((url, json))
                return SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"choices": [{"message": {"content": creative.reply}}]})
        broken.calls.clear()
        with patch.object(w, 'ROAST_FREE_BACKUP_MODEL', 'other:free'), patch.object(w, 'ROAST_POLLINATIONS_FALLBACK', True), patch.object(w, '_creative_client', return_value=broken), patch.object(w.httpx, 'AsyncClient', AnonymousHTTP):
            await w.write_script('personal context', people, [b'private image bytes'], ['image/jpeg'], 'BYOK_PRIVATE', expected_beats=10, off_limits='family')
            assert len(broken.calls) == 2 and len(AnonymousHTTP.calls) == 1
            sent = json.dumps(AnonymousHTTP.calls)
            assert 'red hat' in sent and 'family portrait' not in sent and 'data:image' not in sent and 'BYOK_PRIVATE' not in sent
        vision.calls.clear()
        with patch.object(w, 'ROAST_WRITER_MODEL', 'paid/model'):
            try: await w.write_script('photo', people, [b'photo'], ['image/jpeg'])
            except RuntimeError: pass
            else: raise AssertionError('free-only mode allowed paid model')
            assert not vision.calls
        with patch.object(w, '_creative_client', side_effect=RuntimeError('not configured')):
            try: await w.write_script('photo', people, [b'photo'], ['image/jpeg'])
            except RuntimeError: pass
            else: raise AssertionError('missing config must fail')
            assert not vision.calls
    # Paid profile stays disabled behind free-only guard, and uses the configured
    # Cydonia/Venice chain only when the operator explicitly opts in.
    class SequenceFake(Fake):
        def __init__(self, replies): super().__init__(None); self.replies = list(replies)
        def create(self, **kw):
            self.calls.append(kw)
            value = self.replies.pop(0)
            if isinstance(value, Exception): raise value
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=value))])
    timeout = w.APITimeoutError(request=w.httpx.Request("POST", "https://example.invalid"))
    seq = SequenceFake([timeout, RuntimeError("primary down"), creative.reply])
    with patch.object(w, 'ROAST_WRITER_PROVIDER', 'openrouter'), patch.object(w, 'ROAST_WRITER_PROFILE', 'creative'), patch.object(w, 'ROAST_POLLINATIONS_FALLBACK', False), patch.object(w, 'ROAST_ALLOW_PAID_WRITER_FALLBACK', False), patch.object(w, '_creative_client', return_value=seq):
        with patch.object(w, 'ROAST_FREE_WRITER_ONLY', True):
            try: await w.write_script('offline', people, [], [], expected_beats=10)
            except RuntimeError: pass
            else: raise AssertionError('paid profile bypassed free-only guard')
            assert not seq.calls
        with patch.object(w, 'ROAST_FREE_WRITER_ONLY', False):
            await w.write_script('offline', people, [], [], expected_beats=10, roast_tier='premium')
            assert [call['model'] for call in seq.calls] == [w.ROAST_PAID_PRIMARY_MODEL, w.ROAST_PAID_PRIMARY_MODEL, w.ROAST_PAID_BACKUP_MODEL]
            # Standard shows use the cheaper mid-tier creative model, premium uses the top one.
            assert w.ROAST_PAID_STANDARD_MODEL != w.ROAST_PAID_PRIMARY_MODEL
            seq.calls.clear()
            seq.replies = [timeout, RuntimeError('primary down'), creative.reply]
            await w.write_script('offline', people, [], [], expected_beats=10, roast_tier='standard')
            assert [call['model'] for call in seq.calls] == [w.ROAST_PAID_STANDARD_MODEL, w.ROAST_PAID_STANDARD_MODEL, w.ROAST_PAID_PRIMARY_MODEL]
            assert all(call['max_tokens'] <= w.writer_max_tokens(10) for call in seq.calls)
    assert w.parse_comedy_styles('["savage","absurdist","savage"]') == ['savage','absurdist']
    assert 'absurdist' in w.build_roast_prompt(people, 'Guest', '', 3, False, False, styles=['absurdist'])
    assert 'sarcastic' in w.build_battle_prompt(people[0], people[1], 2, '', '', False, False, False, styles=['sarcastic'])
    try: w.parse_comedy_styles('["unknown"]')
    except ValueError: pass
    else: raise AssertionError('unknown style accepted')
    try: w._normalize_photo_observations('{broken', 1, None)
    except RuntimeError: pass
    else: raise AssertionError('invalid vision JSON accepted')
    b = {'laugh_after':'big','reaction':'laugh','persona_id':'p1'}
    tag = {'type':'tag','persona_id':'p1'}
    assert _hold(b, tag) < _hold(b)
    starts, events, _ = build_timeline([b, tag], [2, 1], 1)
    assert any(t > starts[0] + 2 for t, _, _ in events)
    assert _hold({'laugh_after':'none','reaction':'cheer'}) > .3
    print('PASS: two-stage mock, privacy boundary, failure handling, and reel timing')

asyncio.run(main())

async def provider_pin():
    from config import ROAST_OPENROUTER_PROVIDER_ONLY
    people2 = [{"id": "p1", "name": "One"}]
    lines2 = [{"persona_id": "p1", "type": "joke", "text": f"Pinned endpoint observation joke number {i}.", "laugh_after": "small"} for i in range(4)]
    creative = Fake(json.dumps({"script": lines2}))
    with patch.object(w, 'ROAST_WRITER_PROVIDER', 'openrouter'), patch.object(w, 'ROAST_WRITER_PROFILE', 'free'), \
         patch.object(w, 'ROAST_WRITER_MODEL', 'nvidia/nemotron-3-ultra-550b-a55b:free'), \
         patch.object(w, 'ROAST_FREE_BACKUP_MODEL', ''), patch.object(w, 'ROAST_FREE_WRITER_ONLY', True), \
         patch.object(w, 'ROAST_OPENROUTER_PROVIDER_ONLY', ('venice/fp8',)), patch.object(w, 'ROAST_OPENROUTER_ALLOW_FALLBACKS', 'false'), \
         patch.object(w, 'ROAST_POLLINATIONS_FALLBACK', False), patch.object(w, 'ROAST_ALLOW_PAID_WRITER_FALLBACK', False), \
         patch.object(w, '_creative_client', return_value=creative):
        out = await w.write_script('offline prompt', people2, [], [], None, expected_beats=4)
        assert len(out) == 4
        body = creative.calls[0]['extra_body']
        assert body['provider']['only'] == ['venice/fp8'] and body['provider']['allow_fallbacks'] is False
        assert creative.calls[0]['model'] == 'nvidia/nemotron-3-ultra-550b-a55b:free'
asyncio.run(provider_pin())
print("PASS: OpenRouter provider pinning sends provider.only and allow_fallbacks=false")

async def streaming_handoff():
    people = [{"id": "p1", "name": "One"}]
    lines = [{"persona_id": "p1", "type": "joke", "text": f"Streamed specific joke number {i} about that red hat.",
              "laugh_after": "small"} for i in range(6)]
    payload = json.dumps({"script": lines})
    pieces = [payload[i:i + 37] for i in range(0, len(payload), 37)]  # splits objects across chunks

    class StreamClient:
        def __init__(self):
            self.calls = []
            self.chat = SimpleNamespace(completions=self)

        def create(self, **kw):
            self.calls.append(kw)
            assert kw.get("stream"), "expected a streaming request"
            return iter([SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=p))]) for p in pieces])

    seen = []

    async def on_beat(beat):
        seen.append(beat)

    client = StreamClient()
    with patch.object(w, 'ROAST_WRITER_PROVIDER', 'openrouter'), patch.object(w, 'ROAST_WRITER_PROFILE', 'free'), \
         patch.object(w, 'ROAST_WRITER_MODEL', 'test-model:free'), patch.object(w, 'ROAST_FREE_BACKUP_MODEL', ''), \
         patch.object(w, 'ROAST_FREE_WRITER_ONLY', True), patch.object(w, 'ROAST_STREAM_TTS', True), \
         patch.object(w, 'ROAST_POLLINATIONS_FALLBACK', False), patch.object(w, 'ROAST_ALLOW_PAID_WRITER_FALLBACK', False), \
         patch.object(w, '_creative_client', return_value=client):
        beats = await w.write_script('offline prompt', people, [], [], None, expected_beats=6, on_beat=on_beat)
    assert [b["text"] for b in beats] == [b["text"] for b in seen], "streamed beats must match the final script"
    assert len(seen) == 6 and all(b["persona_id"] == "p1" for b in seen)
    assert client.calls[0]["max_tokens"] <= w.writer_max_tokens(6)
    # A split object must not be emitted twice or dropped halfway.
    partial_state = {"pos": 0}
    assert w._scan_objects('{"a": 1, "b": "x', partial_state) == []
    assert len(w._scan_objects('{"a": 1, "b": "x", "text": "hi"}', partial_state)) == 1

asyncio.run(streaming_handoff())
print("PASS: streamed beats are handed off early and match the final parsed script")

async def progressive_voice():
    from services.voice_orchestrator import voice_beats_progressive
    calls = []

    async def fake_synth(beat, meta, *, byok_eleven=None, byok_openai=None, premium_voices=False):
        calls.append(beat["text"])
        return {"persona_id": beat["persona_id"], "audio_url": f"/api/audio/{len(calls)}.mp3", "provider": "openai"}

    beats = [{"persona_id": "p1", "text": "early line"}, {"persona_id": "p1", "text": "late line"}]
    with patch('services.voice_orchestrator.synthesize_beat', fake_synth):
        # Simulate a task already started while the script was still streaming.
        pending = {"early line": asyncio.create_task(fake_synth({"persona_id": "p1", "text": "early line"}, {}))}
        await asyncio.sleep(0)
        transcript, providers = await voice_beats_progressive(pending, beats, {}, byok_eleven=None, byok_openai=None, premium_voices=False)
    assert [t["audio_url"] for t in transcript] and providers == ["openai"]
    assert calls.count("early line") == 1 and "late line" in calls, "an already-started voice task must be reused, not regenerated"
    assert pending == {}, "unused pre-started tasks are cancelled and cleared"

asyncio.run(progressive_voice())
print("PASS: progressive voice reuses work started during streaming")
