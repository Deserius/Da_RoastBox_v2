"""HD vertical highlight reel (1080x1920 MP4, H.264/AAC, ≤30 s or ≤60 s) for TikTok / Reels / Shorts.

Structure: animated "WELCOME TO DA ROASTBOX!" splash → roaster line-up → hot-seat reveal → the BEST jokes
(ranked by crowd reaction) with word-by-word captions in a persona speech bubble over the photo they reference →
a kinetic branded thank-you / winner outro. Pillow keyframes stream to disk; ffmpeg adds smooth
camera motion and mixes the existing voices with crowd audio.
"""
import io
import logging
import random
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import imageio_ffmpeg
from mutagen.mp3 import MP3
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

log = logging.getLogger(__name__)

ASSETS = Path(__file__).resolve().parent.parent / "assets"
FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
W, H, FPS = 1080, 1920, 30
BG = (5, 5, 5)
ACCENT, GOLD, SOFT, WHITE = (255, 92, 42), (255, 169, 112), (167, 167, 167), (255, 255, 255)
REEL_LENGTHS = (30, 60)
REEL_STYLE_VERSION = "theater-v7-reliable-highlights"

# Voice-first tuning: audible, natural reactions but noticeably softer than
# the older 0.8 mix. Duck the whole crowd bus under every spoken line.
REEL_CROWD_GAIN = 0.42
REEL_ROOM_GAIN = 0.10
SPEECH_DUCK = 0.08
DUCK_ATTACK_S = 0.06
DUCK_RELEASE_S = 0.24

# (gain, layer bank, layer gain, layer delay s, hold s, land s) — mirrors frontend crowdEngine, holds tightened for reels.
LEVELS = {
    "none": (0, None, 0, 0, 0.0, 0.12),
    "small": (0.48, None, 0, 0, 0.65, 0.18),
    "medium": (0.68, "small", 0.22, 0.31, 1.15, 0.20),
    "big": (0.82, "medium", 0.30, 0.40, 1.75, 0.23),
    "explosive": (0.94, "big", 0.38, 0.34, 2.8, 0.25),
}
BANK = {"small": ["chuckle_1", "chuckle_2"], "medium": ["laugh_med_1", "laugh_med_2"],
        "big": ["laugh_big_1", "laugh_big_2"], "explosive": ["explosive_1", "explosive_2"],
        "ooh": ["ooh_1", "ooh_2"], "groan": ["groan_1"], "cheer": ["intro_cheer"]}
POINTS = {"none": 0, "small": 1, "medium": 2, "big": 4, "explosive": 6}
STAMP = {"ooh": "OOOOOH!", "groan": "THE CROWD GROANS", "cheer": "CROWD GOES WILD!",
         "explosive": "STANDING OVATION!", "big": "BIG LAUGH!", "medium": "LAUGHS!", "small": "CHUCKLES"}
SPLASH_S, LINEUP_STEP_S, HOTSEAT_S, OUTRO_S, GAP_S = 2.2, 0.45, 1.8, 2.6, 0.25


def _crowd_duck_expression(voice_windows: List[tuple]) -> str:
    """FFmpeg volume envelope for the crowd bus, on the global reel timeline.

    A short attack completes before each voice starts; the gentle release lets
    the laugh recover afterward. min() handles overlapping/close voice windows
    without raising crowd gain between them. Expressions contain only numeric
    timeline data, never user input.
    """
    expression = "1"
    for start, end in voice_windows:
        start, end = max(0.0, float(start)), max(0.0, float(end))
        if end <= start:
            continue
        attack_start = max(0.0, start - DUCK_ATTACK_S)
        attack_len = max(0.001, start - attack_start)
        rise = 1.0 - SPEECH_DUCK
        one = (f"if(lt(t,{attack_start:.6f}),1,"
               f"if(lt(t,{start:.6f}),1-{rise:.6f}*(t-{attack_start:.6f})/{attack_len:.6f},"
               f"if(lt(t,{end:.6f}),{SPEECH_DUCK:.6f},"
               f"if(lt(t,{end + DUCK_RELEASE_S:.6f}),{SPEECH_DUCK:.6f}+"
               f"{rise:.6f}*(t-{end:.6f})/{DUCK_RELEASE_S:.6f},1))))")
        expression = f"min({expression},{one})"
    return expression


# ---------------------------------------------------------------- drawing helpers
@lru_cache(maxsize=64)
def _font(size: int, display: bool = True):
    return ImageFont.truetype(str(ASSETS / "fonts" / ("BebasNeue-Regular.ttf" if display else "Oswald.ttf")), size)


def _hex(c: Optional[str]):
    try:
        c = (c or "#ff5c2a").lstrip("#")
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except Exception:
        return ACCENT


def _cover(img, size):
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS)


def _circle(img, d: int, ring):
    image = _cover(img, (d, d))
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d, d), fill=255)
    out = Image.new("RGBA", (d + 16, d + 16), (0, 0, 0, 0))
    ImageDraw.Draw(out).ellipse((0, 0, d + 15, d + 15), fill=ring)
    out.paste(image, (8, 8), mask)
    return out


def _backdrop(photo=None, glow=ACCENT):
    base = Image.new("RGB", (W, H), (7, 4, 4))
    if photo:
        blurred = _cover(photo, (W, H)).filter(ImageFilter.GaussianBlur(45))
        base = Image.blend(base, blurred, 0.30)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((-420, -540, W + 420, 850), fill=78)
    base.paste(Image.new("RGB", (W, H), glow), (0, 0), mask.filter(ImageFilter.GaussianBlur(115)))
    return base


def _fit_font(d, text, max_width, start=64, minimum=30, display=True):
    size = start
    while size > minimum and d.textlength(text, font=_font(size, display)) > max_width:
        size -= 2
    return _font(size, display)


def _wrap(d, text, font, max_w):
    """Wrap even a single very long word instead of drawing past the safe area."""
    words = []
    for word in text.split():
        if d.textlength(word, font=font) <= max_w:
            words.append(word)
            continue
        part = ""
        for char in word:
            if part and d.textlength(part + char, font=font) > max_w:
                words.append(part)
                part = char
            else:
                part += char
        if part:
            words.append(part)
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if current and d.textlength(trial, font=font) > max_w:
            lines.append(current)
            current = word
        else:
            current = trial
    return lines + ([current] if current else [])


def _brand(d):
    # Keep vital content away from the extreme top/bottom and the social-app side rail.
    d.rounded_rectangle((82, 102, 190, 153), radius=14, fill=ACCENT)
    d.text((136, 127), "LIVE", font=_font(35), fill=(25, 8, 4), anchor="mm")
    d.text((W // 2, 132), "DA ROASTBOX!", font=_font(70), fill=GOLD, anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
    d.text((W // 2, H - 128), "18+  /  THE MIC IS HOT", font=_font(29, False), fill=(203, 174, 158), anchor="mm")


def _sparks(d, phase=0.0):
    """Small deterministic ember motion, drawn into each scene keyframe."""
    for i in range(22):
        x = 55 + ((i * 173 + (i % 3) * 29) % (W - 110))
        y = H - 250 - ((i * 229 + int(phase * 195)) % (H - 410))
        r = 2 + i % 4
        color = (255, 155 + i % 75, 46) if i % 3 else (255, 92, 42)
        d.ellipse((x - r, y - r, x + r, y + r), fill=color)


def _photo_card(base, photo, top, h, ring=ACCENT):
    if not photo:
        return
    card = _cover(photo, (W - 196, h))
    mask = Image.new("L", card.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, card.width - 1, card.height - 1), radius=38, fill=255)
    ImageDraw.Draw(base).rounded_rectangle((92, top - 6, W - 92, top + h + 6), radius=44, fill=ring)
    base.paste(card, (98, top), mask)


@lru_cache(maxsize=1)
def _stage_shade():
    mask = Image.new("L", (1, H), 0)
    for y in range(H):
        # Light top vignette, dark lower third under captions.
        top = max(0, 110 - y // 4)
        bottom = max(0, min(225, int((y - 790) * 0.29)))
        mask.putpixel((0, y), max(top, bottom))
    return mask.resize((W, H))


def _stage_backdrop(photo, color):
    base = _backdrop(photo, color)
    if photo:
        # Fit rather than crop the guest, with a softly blurred edge fill.
        focus = ImageOps.contain(photo.convert("RGB"), (W, 1480), Image.LANCZOS)
        base.paste(focus, ((W - focus.width) // 2, 220 + (1480 - focus.height) // 2))
    base.paste(Image.new("RGB", (W, H), (3, 2, 3)), (0, 0), _stage_shade())
    return base


def _bubble(img, persona, portrait, words_shown: List[str], all_words: List[str], progress: float):
    """A fixed-height, rolling caption with a highlighted current word."""
    d = ImageDraw.Draw(img)
    color = ACCENT
    font = _font(58, False)
    full = _wrap(d, " ".join(all_words).upper(), font, W - 260)
    if len(full) > 7:
        font = _font(51, False)
        full = _wrap(d, " ".join(all_words).upper(), font, W - 260)
    visible = _wrap(d, " ".join(words_shown).upper(), font, W - 260)[-4:]
    line_h = font.size + 15
    lines = max(1, min(4, len(full)))
    box_h = 66 + lines * line_h
    bottom = 1624
    top = bottom - box_h
    d.rounded_rectangle((86, top, W - 86, bottom), radius=32, fill=(15, 11, 10), outline=color, width=4)
    d.rounded_rectangle((86, top, 98, bottom), radius=5, fill=color)
    if portrait:
        avatar = _circle(portrait, 122, color)
        img.paste(avatar, (92, top - 150), avatar)
    d.text((252, top - 113), "ON THE MIC", font=_font(27, False), fill=(235, 211, 196), anchor="lm")
    name = (persona.get("displayName") or persona.get("name") or "ROASTER").upper()
    d.text((250, top - 58), name, font=_fit_font(d, name, W - 340, 68, 34), fill=color,
           anchor="lm", stroke_width=2, stroke_fill=(0, 0, 0))
    y = top + 31
    for i, line in enumerate(visible):
        # The newest word pops in gold while the rest remains high contrast.
        if i == len(visible) - 1:
            prefix, sep, last = line.rpartition(" ")
            if not sep:
                prefix, last = "", line
            if prefix:
                d.text((128, y), prefix + " ", font=font, fill=WHITE)
            x = 128 + d.textlength(prefix + " ", font=font) if prefix else 128
            d.text((x, y), last, font=font, fill=GOLD)
        else:
            d.text((128, y), line, font=font, fill=WHITE)
        y += line_h
    d.rounded_rectangle((100, 1680, W - 100, 1690), radius=5, fill=(62, 48, 42))
    d.rounded_rectangle((100, 1680, 100 + max(10, int((W - 200) * max(0, min(1, progress)))), 1690), radius=5, fill=color)


# ---------------------------------------------------------------- scene renderers
def splash_frames():
    base = _backdrop(glow=(255, 81, 25))
    steps = 10
    for i in range(steps):
        k = (i + 1) / steps
        img = base.copy()
        d = ImageDraw.Draw(img)
        _sparks(d, i / steps)
        for ring in range(3):
            radius = int((245 + ring * 95) * (0.74 + 0.26 * k))
            d.ellipse((W // 2 - radius, 875 - radius, W // 2 + radius, 875 + radius),
                      outline=(92 - ring * 13, 34 - ring * 4, 15), width=3)
        d.rounded_rectangle((410, 495, 670, 552), radius=18, fill=ACCENT)
        d.text((W // 2, 524), "LIVE  /  18+", font=_font(34, False), fill=(30, 9, 3), anchor="mm")
        d.text((W // 2, 690), "WELCOME TO", font=_font(74), fill=WHITE, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
        title = "DA ROASTBOX!"
        title_font = _fit_font(d, title, 890, int(130 + 38 * k), 70)
        d.text((W // 2 + 4, 870 + 8), title, font=title_font, fill=(72, 13, 4), anchor="mm", stroke_width=7, stroke_fill=(20, 5, 2))
        d.text((W // 2, 870), title, font=title_font, fill=GOLD, anchor="mm", stroke_width=3, stroke_fill=ACCENT)
        d.text((W // 2, 1035), "THE MIC IS HOT", font=_font(50, False), fill=(255, 223, 190), anchor="mm")
        d.text((W // 2, 1115), "THE CROWD IS READY. THE HEAT IS ON.", font=_font(30, False), fill=(228, 165, 125), anchor="mm")
        yield img, SPLASH_S / steps
    base.close()


def lineup_frames(personas: List[dict], portraits: Dict[str, Image.Image], title: str):
    n = len(personas)
    base = _backdrop()
    if not n:
        img = base.copy()
        d = ImageDraw.Draw(img)
        _brand(d)
        d.text((W // 2, 450), title, font=_fit_font(d, title, 880, 100), fill=GOLD, anchor="mm")
        yield img, 0.6
    cols = 2 if n > 1 else 1
    size = 300 if n <= 2 else 240
    rows = (n + cols - 1) // cols
    first_center_y = 940 - max(0, rows - 1) * (size + 150) // 2
    for k in range(1, n + 1):
        # Each comic pops in over three keyframes, then holds in the final line-up.
        for frame, scale in enumerate((0.82, 1.07, 1.0)):
            img = base.copy()
            d = ImageDraw.Draw(img)
            _sparks(d, (k * 3 + frame) / max(1, n * 3))
            _brand(d)
            d.text((W // 2, 280), "MAKE SOME NOISE FOR", font=_font(34, False), fill=(229, 173, 126), anchor="mm")
            d.text((W // 2, 364), title, font=_fit_font(d, title, 890, 96), fill=GOLD, anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
            for i, p in enumerate(personas[:k]):
                row, col = divmod(i, cols)
                cx = W // 2 if cols == 1 or (i == n - 1 and n % 2 == 1) else (W // 4 if col == 0 else 3 * W // 4)
                cy = first_center_y + row * (size + 150)
                actual = int(size * scale) if i == k - 1 else size
                if portraits.get(p["id"]):
                    avatar = _circle(portraits[p["id"]], actual, ACCENT)
                    img.paste(avatar, (cx - avatar.width // 2, cy - avatar.height // 2), avatar)
                name = (p.get("displayName") or p.get("name") or "ROASTER").upper()
                d.text((cx, cy + size // 2 + 50), name, font=_fit_font(d, name, 440, 52, 28), fill=ACCENT,
                       anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
            dur = LINEUP_STEP_S / 3
            if k == n and frame == 2:
                dur += 0.6
            yield img, dur
    base.close()


def hotseat_frame(photo, subject_name: Optional[str], battle: bool) -> Image.Image:
    img = _backdrop(photo)
    d = ImageDraw.Draw(img)
    _brand(d)
    d.text((W // 2, 260), "ALL EYES ON YOU", font=_font(40, False), fill=(255, 209, 155), anchor="mm")
    if photo:
        _photo_card(img, photo, 330, 880, GOLD)
    else:
        d.ellipse((280, 400, 800, 920), fill=(72, 29, 17), outline=GOLD, width=7)
        d.text((W // 2, 660), "THE HOT SEAT", font=_font(85), fill=GOLD, anchor="mm")
    label = "ROAST BATTLE" if battle else "IN THE HOT SEAT"
    d.text((W // 2, 1320), label, font=_fit_font(d, label, 900, 112), fill=GOLD, anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
    name = (subject_name or ("OUR BRAVE GUEST" if not battle else "THE MAIN EVENT")).upper()
    name_font = _fit_font(d, name, 870, 80, 34)
    for i, line in enumerate(_wrap(d, name, name_font, 870)[:2]):
        d.text((W // 2, 1430 + i * 84), line, font=name_font, fill=WHITE, anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
    d.text((W // 2, 1610), "TURN UP THE HEAT", font=_font(38, False), fill=(255, 170, 111), anchor="mm")
    return img


def hotseat_frames(photo, subject_name, battle, extra_end=0.0):
    base = hotseat_frame(photo, subject_name, battle)
    for i in range(6):
        img = base.copy()
        d = ImageDraw.Draw(img)
        _sparks(d, i / 6)
        # The first joke starts after a short breath; hold the reveal rather
        # than showing its first caption before its voice begins.
        yield img, HOTSEAT_S / 6 + (extra_end if i == 5 else 0.0)
    base.close()


def _stamp(img, text, strength=1.0):
    layer = Image.new("RGBA", (810, 150), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((8, 8, 802, 142), radius=28, fill=ACCENT + (245,), outline=(255, 210, 117, 255), width=5)
    d.text((405, 75), text, font=_fit_font(d, text, 720, 95, 36), fill=WHITE,
           anchor="mm", stroke_width=3, stroke_fill=(0, 0, 0))
    if strength != 1.0:
        layer = layer.resize((int(layer.width * strength), int(layer.height * strength)), Image.Resampling.LANCZOS)
    layer = layer.rotate(-4, resample=Image.Resampling.BICUBIC, expand=True)
    img.paste(layer, ((W - layer.width) // 2, 880 - layer.height // 2), layer)


def beat_frames(beat, persona, portrait, photo, duration: float, hold: float, chip: str):
    words = beat.get("text", "").split() or ["…"]
    # Closely spaced keyframes plus the continuous camera move retain natural timing
    # without holding hundreds of full-HD images in memory.
    steps = min(len(words), max(12, min(28, int(duration * 4))), max(1, int(duration / 0.04)))
    base = _stage_backdrop(photo, ACCENT)
    d = ImageDraw.Draw(base)
    _brand(d)
    if chip:
        chip_font = _fit_font(d, chip, 840, 38, 24, False)
        d.text((W // 2, 218), chip, font=chip_font, fill=(255, 220, 181), anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0))
    hold_frame = None
    for s in range(1, steps + 1):
        img = base.copy()
        _sparks(ImageDraw.Draw(img), s / steps)
        _bubble(img, persona, portrait, words[:max(1, round(len(words) * s / steps))], words, s / steps)
        if s == steps and hold > 0.05:
            hold_frame = img.copy()
        yield img, duration / steps
    base.close()
    stamp = STAMP.get(beat.get("reaction") if beat.get("reaction") in ("ooh", "groan", "cheer") else beat.get("laugh_after"))
    if hold_frame is not None:
        if stamp and hold > 0.16:
            # A short kinetic pop, then the reaction stays readable for the hold.
            n = 3
            frame_dur = min(0.12, hold / (n + 1))
            for scale in (0.70, 1.12, 1.0):
                img = hold_frame.copy()
                _stamp(img, stamp, scale)
                yield img, frame_dur
            _stamp(hold_frame, stamp)
            yield hold_frame, max(0.04, hold - frame_dur * n)
        else:
            yield hold_frame, hold


def outro_frame(photo, battle: Optional[dict], personas: Dict[str, dict], subject_name: Optional[str] = None) -> Image.Image:
    img = _backdrop(photo)
    d = ImageDraw.Draw(img)
    _brand(d)
    d.text((W // 2, 300), "ONE MORE ROUND OF APPLAUSE", font=_font(36, False), fill=(244, 183, 135), anchor="mm")
    if battle:
        winner = personas.get(battle.get("winner"), {})
        d.text((W // 2, 480), "WINNER", font=_font(118), fill=GOLD, anchor="mm", stroke_width=4, stroke_fill=(0, 0, 0))
        name = (winner.get("displayName") or "THE CROWD").upper()
        d.text((W // 2, 610), name, font=_fit_font(d, name, 870, 120, 36), fill=ACCENT, anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
        y = 785
        for pid, score in list(battle.get("scores", {}).items())[:4]:
            label = f"{(personas.get(pid, {}).get('displayName') or pid).upper()}  —  {score} PTS"
            d.text((W // 2, y), label, font=_fit_font(d, label, 850, 58, 28), fill=WHITE, anchor="mm")
            y += 80
    else:
        if photo:
            avatar = _circle(photo, 470, GOLD)
            img.paste(avatar, ((W - avatar.width) // 2, 390), avatar)
        d.text((W // 2, 1050), "THE HOT SEAT SURVIVED", font=_fit_font(d, "THE HOT SEAT SURVIVED", 890, 96), fill=ACCENT,
               anchor="mm", stroke_width=5, stroke_fill=(0, 0, 0))
        guest = (subject_name or "OUR BRAVE GUEST").upper()
        thanks = f"THANK YOU, {guest}!"
        thanks_font = _fit_font(d, thanks, 870, 65, 36)
        for i, line in enumerate(_wrap(d, thanks, thanks_font, 870)[:2]):
            d.text((W // 2, 1180 + i * 62), line, font=thanks_font, fill=WHITE, anchor="mm")
    d.text((W // 2, 1400), "THANK YOU EVERYBODY FOR COMING", font=_font(39, False), fill=(232, 187, 153), anchor="mm")
    d.text((W // 2, 1500), "WHERE PEOPLE COME TO GET ROASTED", font=_font(48), fill=GOLD, anchor="mm")
    d.text((W // 2, 1565), "AND LEAVE BURNT CRISPY.", font=_font(63), fill=ACCENT, anchor="mm")
    return img


def outro_frames(photo, battle, personas, subject_name, duration):
    base = outro_frame(photo, battle, personas, subject_name)
    for i in range(8):
        img = base.copy()
        _sparks(ImageDraw.Draw(img), i / 8)
        yield img, duration / 8
    base.close()


# ---------------------------------------------------------------- planning
def intro_length(n_personas: int) -> float:
    return SPLASH_S + LINEUP_STEP_S * n_personas + 0.6 + HOTSEAT_S


def _hold(beat, next_beat=None) -> float:
    if "_reel_hold_s" in beat:
        return max(0.0, min(3.0, float(beat["_reel_hold_s"])))
    gain, _, _, _, hold, land = LEVELS.get(beat.get("laugh_after") or "none", LEVELS["small"])
    reaction = beat.get("reaction") or "laugh"
    extra = 0.6 if reaction in ("ooh", "groan") else 0.0
    result = land + extra + (hold if gain else 1.0) if (gain or reaction != "laugh") else 0.3
    if beat.get("rapid_fire") and (next_beat or {}).get("rapid_fire"):
        return min(0.9, result * 0.45)
    if (next_beat or {}).get("type") == "tag" and (next_beat or {}).get("persona_id") == beat.get("persona_id"):
        return result * 0.45
    return result


def _is_bookend(beat: dict) -> bool:
    # Full-show announcements and the long formal thank-you are NOT highlights.
    # Older saved shows predate the show_signoff marker, so recognize their motto.
    return bool(beat.get("stage") or beat.get("type") == "intro" or beat.get("show_signoff") or
                "where people come to get roasted and leave burnt crispy" in (beat.get("text") or "").lower())


def select_highlights(beats: List[dict], durations: List[float], max_seconds: int, n_personas: int,
                      *, intro_seconds: Optional[float] = None, outro_seconds: float = OUTRO_S) -> List[int]:
    """Best complete jokes in show order, not the full show's introductions/outro.

    Dependent tags/replies travel with their immediately preceding setup instead
    of becoming a context-free half-joke. Unknown legacy beats remain eligible.
    """
    budget = max_seconds - (intro_length(n_personas) if intro_seconds is None else intro_seconds) - outro_seconds - 0.08
    def score(i):
        b = beats[i]
        return (POINTS.get(b.get("laugh_after"), 0) * 10 + (6 if b.get("reaction") == "ooh" else 0)
                + (8 if b.get("type") == "closer" else 0) + (4 if b.get("type") == "punchline" else 0) - durations[i] * 0.5)
    ranked = sorted((i for i, b in enumerate(beats) if not _is_bookend(b)), key=score, reverse=True)
    chosen, used = set(), 0.0
    for i in ranked:
        group = [i]
        start = i
        # Preserve an explicit dependent handoff, with a small bounded context
        # chain. Do not drag the full show's entrance into the highlight.
        while start > 0 and (beats[start].get("_standalone") is False or
                              beats[start].get("type") in {"tag", "callback"}):
            if _is_bookend(beats[start - 1]):
                break
            start -= 1
            group.insert(0, start)
            if len(group) >= 3:
                break
        missing = [index for index in group if index not in chosen]
        cost = sum(durations[j] + _hold(beats[j]) + GAP_S for j in missing)
        if missing and used + cost <= budget:
            chosen.update(missing)
            used += cost
    return sorted(chosen)


def highlight_plan(beats: List[dict], durations: List[float], max_seconds: int, n_personas: int):
    """Prefer the normal entrance; compact it if a long complete joke needs room.

    This fixes the common 30s failure where a 20-24s voiced joke used to be
    rejected solely because the title/cast/reveal occupied the remaining time.
    Speech is NEVER sliced to fit or replaced with a silent fake export.
    """
    picked = select_highlights(beats, durations, max_seconds, n_personas)
    if picked:
        return picked, beats, 1.0, OUTRO_S
    intro_scale, outro_s = 0.42, 1.1
    compact = [dict(b, _reel_hold_s=min(0.45, _hold(b))) for b in beats]
    picked = select_highlights(compact, durations, max_seconds, n_personas,
                               intro_seconds=intro_length(n_personas) * intro_scale, outro_seconds=outro_s)
    if not picked:
        hint = "Choose the 60s reel to keep the whole punchline." if max_seconds == 30 else "Try a show with shorter joke lines."
        raise ValueError(f"No complete joke fits this {max_seconds}s reel. {hint}")
    return picked, compact, intro_scale, outro_s


def build_timeline(beats: List[dict], durations: List[float], n_personas: int,
                   *, intro_seconds: Optional[float] = None, outro_seconds: float = OUTRO_S):
    """Returns (beat_starts, reaction_events[(t, bank, gain)], total_seconds) for the selected beats."""
    t = intro_length(n_personas) if intro_seconds is None else intro_seconds
    starts, events = [], [(0.1, "cheer", 0.8), (SPLASH_S, "cheer", 0.5)]
    for i, beat in enumerate(beats):
        t += GAP_S
        starts.append(t)
        t += durations[i]
        gain, layer, lgain, ldelay, _, land = LEVELS.get(beat.get("laugh_after") or "none", LEVELS["small"])
        reaction = beat.get("reaction") or "laugh"
        extra = 0.0
        if reaction in ("ooh", "groan"):
            events.append((t + land, reaction, 0.85 if reaction == "ooh" else 0.7))
            extra = 0.6
        elif reaction == "cheer":
            events.append((t + land + 0.2, "cheer", 0.6))
        if gain > 0:
            events.append((t + land + extra, beat.get("laugh_after"), gain))
            if layer:
                events.append((t + land + extra + ldelay, layer, lgain))
        t += _hold(beat, beats[i + 1] if i + 1 < len(beats) else None)
    return starts, events, t + outro_seconds


# ---------------------------------------------------------------- render
def _run(cmd: List[str]):
    proc = subprocess.run(cmd, capture_output=True, timeout=600)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.decode(errors="ignore")[-800:])


def render_reel(*, beats: List[dict], voice_files: List[Optional[bytes]], personas: Dict[str, dict],
                photos: List[bytes], subject_name: Optional[str], battle: Optional[dict], max_seconds: int = 60, battle_style: str = "classic") -> bytes:
    if max_seconds not in REEL_LENGTHS:
        raise ValueError("Choose a 30s or 60s reel.")
    if not beats:
        raise ValueError("This show has no roast lines to export.")
    rng = random.Random(42)
    images = []
    for photo in photos:
        try:
            if photo:
                images.append(Image.open(io.BytesIO(photo)).convert("RGB"))
        except (OSError, ValueError):
            log.warning("Skipping an unreadable subject image during reel render")
    # The route supplies the selected cast in show order. Include everyone in
    # the entrance even if the generated transcript happened to omit a comic.
    lineup = list(personas.values())[:5]
    portraits = {}
    for pid, p in personas.items():
        fp = ASSETS / "personas" / Path(p.get("image", "")).name
        portraits[pid] = Image.open(fp).convert("RGB") if fp.exists() else None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        all_durations, voice_paths = [], []
        for i, beat in enumerate(beats):
            data = voice_files[i] if i < len(voice_files) else None
            fp = None
            if data:
                fp = tmp / f"v{i}.mp3"
                fp.write_bytes(data)
                all_durations.append(MP3(str(fp)).info.length)
            else:
                all_durations.append(min(8.0, len(beats[i].get("text", "").split()) * 0.32))
            voice_paths.append(fp)
        picked, export_beats, intro_scale, outro_s = highlight_plan(beats, all_durations, max_seconds, len(lineup))
        sel = [export_beats[i] for i in picked]
        durs = [all_durations[i] for i in picked]
        starts, events, total = build_timeline(sel, durs, len(lineup),
                                              intro_seconds=intro_length(len(lineup)) * intro_scale,
                                              outro_seconds=outro_s)
        total = min(total, float(max_seconds))

        # ---- frames
        # Save each full-HD frame immediately. Keeping the whole show in Pillow images
        # can exceed a small host's memory and kill the API during a 30/60s export.
        concat, count, used = [], 0, 0.0

        def write_frames(sequence):
            nonlocal count, used
            for img, dur in sequence:
                fp = tmp / f"f{count:04d}.jpg"
                try:
                    img.save(fp, quality=88)
                finally:
                    img.close()
                emitted = max(0.04, dur)
                concat.extend([f"file '{fp}'", f"duration {emitted:.3f}"])
                count += 1
                used += emitted

        title = "TONIGHT'S ROASTERS" if not battle else "ROAST BATTLE"
        def entrance_frames(sequence):
            for img, dur in sequence:
                yield img, dur * intro_scale

        write_frames(entrance_frames(splash_frames()))
        write_frames(entrance_frames(lineup_frames(lineup, portraits, title)))
        write_frames(entrance_frames(hotseat_frames(images[0] if images else None, subject_name, bool(battle),
                                                     extra_end=GAP_S / intro_scale)))
        running = {pid: 0 for pid in (battle or {}).get("scores", {})}
        for k, beat in enumerate(sel):
            pid = beat["persona_id"]
            chip = ""
            if battle and pid in running:
                running[pid] += POINTS.get(beat.get("laugh_after"), 0)
                chip = "   ·   ".join(f"{personas.get(x, {}).get('displayName', x).upper()} {v}" for x, v in running.items())
            photo = images[min(max(0, beat.get("image_index") or 0), len(images) - 1)] if images else None
            next_beat = sel[k + 1] if k + 1 < len(sel) else None
            write_frames(beat_frames(beat, personas.get(pid, {}), portraits.get(pid), photo, durs[k],
                                     _hold(beat, next_beat) + (GAP_S if next_beat else 0.0), chip))
        write_frames(outro_frames(images[0] if images else None, battle, personas, subject_name, max(0.1, total - used)))
        concat.append(f"file '{tmp / f'f{count - 1:04d}.jpg'}'")
        (tmp / "frames.txt").write_text("\n".join(concat))

        # ---- audio: keep voice on its own bus. Duck the combined room and
        # reaction bus over every voiced interval, including overlapping tails,
        # rather than merely reducing each reaction's initial gain.
        sfx = ASSETS / "sfx"
        inputs = ["-stream_loop", "-1", "-i", str(sfx / "room_tone.mp3")]
        filters = [f"[0:a]atrim=0:{total:.2f},volume={REEL_ROOM_GAIN:.2f},afade=t=out:st={max(0, total - 2):.2f}:d=2[a0]"]
        crowd_labels, voice_labels = ["[a0]"], []
        next_input = 1

        def add(path: Path, at: float, vol: float, destination: list):
            nonlocal next_input
            idx, next_input = next_input, next_input + 1
            inputs.extend(["-i", str(path)])
            ms = int(max(0, at) * 1000)
            filters.append(f"[{idx}:a]volume={vol:.2f},adelay={ms}|{ms}[a{idx}]")
            destination.append(f"[a{idx}]")

        voice_windows = []
        for k, i in enumerate(picked):
            if voice_paths[i]:
                add(voice_paths[i], starts[k], 1.0, voice_labels)
                voice_windows.append((starts[k], starts[k] + durs[k]))
        last_sample = {}
        for at, bank, gain in events:
            if at < total:
                choices = [name for name in BANK[bank] if name != last_sample.get(bank)] or BANK[bank]
                name = rng.choice(choices)
                last_sample[bank] = name
                add(sfx / f"{name}.mp3", at, gain * REEL_CROWD_GAIN, crowd_labels)
        add(sfx / "applause_outro.mp3", max(0, total - outro_s), 0.39, crowd_labels)
        expression = _crowd_duck_expression(voice_windows)
        filters.append(f"{''.join(crowd_labels)}amix=inputs={len(crowd_labels)}:normalize=0:dropout_transition=0,"
                       f"volume='{expression}':eval=frame[crowd]")
        labels = ["[crowd]", *voice_labels]
        if battle_style == "rap" and (sfx / "rap_beat.mp3").is_file():
            idx = next_input
            inputs.extend(["-stream_loop", "-1", "-i", str(sfx / "rap_beat.mp3")])
            # Same duck envelope as reactions; instrumental begins at first bar.
            start = max(0, starts[0])
            ms = int(start * 1000)
            filters.append(f"[{idx}:a]atrim=0:{max(0.1, total-start):.2f},volume=0.20,adelay={ms}|{ms},"
                           f"volume='{expression}':eval=frame[rapmusic]")
            labels.append("[rapmusic]")
        filters.append(f"{''.join(labels)}amix=inputs={len(labels)}:normalize=0:dropout_transition=0,"
                       f"alimiter=limit=0.95,atrim=0:{total:.2f},afade=t=out:st={max(0, total - 0.6):.2f}:d=0.6[mix]")
        (tmp / "filter.txt").write_text(";".join(filters))
        _run([FFMPEG, "-y", "-loglevel", "error", "-filter_complex_threads", "1", *inputs, "-filter_complex", ";".join(filters),
              "-map", "[mix]", "-ar", "44100", "-ac", "2", "-c:a", "pcm_s16le", str(tmp / "mix.wav")])
        out = tmp / "reel.mp4"
        _run([FFMPEG, "-y", "-loglevel", "error", "-filter_threads", "1", "-filter_complex_threads", "1",
              "-f", "concat", "-safe", "0", "-i", str(tmp / "frames.txt"),
              "-i", str(tmp / "mix.wav"), "-vf",
              (f"fps={FPS},zoompan=z='1.018+0.012*sin(on/55)':"
               f"x='iw/2-iw/zoom/2+10*sin(on/75)':y='ih/2-ih/zoom/2+16*cos(on/85)':"
               f"d=1:s={W}x{H}:fps={FPS},scale=out_range=tv,format=yuv420p"), "-pix_fmt", "yuv420p",
              "-c:v", "libx264", "-threads", "2", "-preset", "veryfast", "-crf", "20", "-c:a", "aac", "-b:a", "192k",
              "-movflags", "+faststart", "-t", f"{total:.2f}", str(out)])
        return out.read_bytes()
