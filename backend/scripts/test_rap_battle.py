#!/usr/bin/env python3
"""Offline checks only: no provider, paid calls, or database."""
import asyncio, json, sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from services import roast_writer as w
from services.voice_orchestrator import acting_instructions
from models import RoastRecord
from services.highlight_reel import _crowd_duck_expression

people = [{'id':'p1','displayName':'One'}, {'id':'p2','displayName':'Two'}]
lines = [{'persona_id': 'p1' if i % 2 == 0 else 'p2', 'text':f'A distinct clever punchline number {i} surprises everyone.', 'type':'joke'} for i in range(10)]
class Fake:
    def __init__(self, result):
        self.result = result; self.calls=[]; self.chat=SimpleNamespace(completions=self)
    def create(self, **kw):
        self.calls.append(kw)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(self.result)))])
async def test():
    vision = Fake({'photos':[{'image_index':0,'details':['guest blue hat']},{'image_index':1,'details':['fighter red jacket']},{'image_index':2,'details':['fighter green cap']}]})
    writer = Fake({'script':lines})
    with patch.object(w,'ROAST_WRITER_PROVIDER','openrouter'), patch.object(w,'OPENROUTER_API_KEY','fake'), patch.object(w,'ROAST_WRITER_MODEL','fake:free'), patch.object(w,'ROAST_FREE_WRITER_ONLY',True), patch.object(w,'ROAST_WRITER_PROFILE','free'), patch.object(w,'get_client',return_value=vision), patch.object(w,'_creative_client',return_value=writer):
        await w.write_script('test', people, [b'guest'], ['image/jpeg'], expected_beats=10, persona_portraits=[{'id':'p1','data':b'portrait1','type':'image/webp'}, {'id':'p2','data':b'portrait2','type':'image/webp'}])
        payload=json.dumps(writer.calls)
        assert 'guest blue hat' in payload and 'fighter red jacket' in payload and 'fighter green cap' in payload
        assert 'fictional_persona_portraits' in payload and 'guest_photos' in payload
        assert 'data:image' not in payload and 'portrait1' not in payload
        assert len(vision.calls)==1 and len(writer.calls)==1
    prompt = w.build_battle_prompt(*people, 2, None, None, False, False, False, rap=True, adult=False, off_limits='family')
    assert 'RAP BATTLE MODE' in prompt and 'family' in prompt and 'CLEAN' in prompt
    assert 'spoken' in acting_instructions({}, {'rap_delivery': True}).lower()
    assert RoastRecord(user_id='u', persona_ids=['p1','p2']).battle_style == 'classic'
    assert (Path(__file__).resolve().parents[1]/'assets/sfx/rap_beat.mp3').stat().st_size > 1000
    assert 'if(' in _crowd_duck_expression([(5,8)])
    print('PASS: rap prompts, portrait separation/privacy, classic default, spoken delivery and local beat')
asyncio.run(test())
