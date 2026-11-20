# Roast-show format: staged, host-voiced introductions

New roast shows open with this voiced sequence. The timing follows each audio
clip, not a fixed countdown. Classic/rap battles keep their separate battle format.

| Beat | Stage | What the theater shows and says |
| --- | --- | --- |
| 1 | `open_host` | Brand title card: "Welcome to Da RoastBox! Where we have a New Victim tonight that we are gonna hit with the flame thrower." |
| 2 | `open_lineup` | Title card: "Lets introduce the line up of your favorite comics that know how to cook and always bring that heat." |
| 3… | `open_persona` | One large comic portrait at a time. The **host** announces the comic, then lands **one joke about that fictional comic's name or character**. The spoken line also appears as a timed caption. |
| last | `open_guest` | Large subject photo, guest name and voiced hot-seat reveal. |

Example: "Tonight's lineup, we have Lil Glizzy. With a name like that, we know
who's got stock in Oscar Mayer." There is no generic "I came to cook" walk-on.

After the guest reveal, the selected comics perform the personalized set. The
finale tightens into rapid-fire punches; the host then thanks the guest and room,
ending with the Da RoastBox "leave burnt crispy" motto.

## Writing and fallback

The existing writing call requests a separate `lineup_roasts` map with one short
joke per selected persona. These jokes are **not** counted as core roast turns and
do not require another LLM call. Missing, malformed, duplicate, obviously profane
in clean mode, or exact off-limits material falls back to the curated collection
in `backend/data/lineup_roasts.json` (two original one-liners for all 40 personas).
The model remains responsible for semantic boundaries and comedic quality; local
checks do not prove that every joke is funny or that every boundary is understood.

## Speaker and portrait are separate

- `persona_id`: the **speaking host**, so introductions keep one consistent voice.
- `introduced_persona_id`: the comic being announced and pictured.
- `media`: that comic's public portrait path.
- `persona_index`: order within the selected cast.
- `stage`: controls the opening scene.

The theater falls back to `persona_id` for older staged shows. Very old shows with
no stages retain their original timed entrance. Existing saved transcripts and
audio are **not rewritten** or recharged; generate a new show for the new intro.

Each opening card is voiced, so it has a speech request like any other beat.
Progressive voice synthesis reuses early audio, but the final show script remains
authoritative: provisional beat types/private metadata cannot overwrite the staged
opening or rapid-fire flags.

## Regression checks

```bash
# Offline: no provider calls
python backend/scripts/test_lineup_roasts.py
python backend/scripts/test_roast_showrunner.py
python backend/scripts/test_two_stage_writer.py

# Optional LIVE writer/TTS check using a synthetic image (operator provider costs)
python scripts/test_lineup_api.py
# Replays that saved show; no new writer/TTS calls
python scripts/test_lineup_show_ui.py
```
