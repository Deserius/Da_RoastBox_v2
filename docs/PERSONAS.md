# Persona Roster (40)

Source of truth: `backend/data/personas.json`. Portraits: `frontend/public/assets/personas/`.

| ID | Stage name | Role | Tier | Inspired by | Tagline | New in v6 |
|---|---|---|---|---|---|---|
| `persona_1` | Big Sun-K | Host / Emcee | free | Jamie Foxx | Smooth sarcasm with a wink |  |
| `persona_2` | Nana Snap | Grandma Comic | free | Betty White | Cute face, filthy mouth |  |
| `persona_3` | Gl1tch | Cyber Comic | free | Michael Blaustein | Online venom, NSFW edition |  |
| `persona_4` | C-Stack | Corporate Roaster | free | Bill Burr | Boardroom burns, bedroom losses |  |
| `persona_5` | Verse King | Poet / MC | free | D.C. Young Fly | Bars that bury you |  |
| `persona_6` | LAN G | Gamer | free | Bo Burnham | 0-and-the-whole-server |  |
| `persona_7` | Calm G | Zen Comic | free | Steven Wright | Quiet, lethal, NSFW |  |
| `persona_8` | Stage G | Show Host | free | Wanda Sykes | Reality-TV ratchet, R-rated |  |
| `persona_9` | Brew G | Barista | free | Iliza Shlesinger | Hot, bitter, NSFW |  |
| `persona_10` | Big Mic G | Announcer | free | Don Rickles | Vintage voice, modern filth |  |
| `persona_11` | Doc G | Scientist Comic | free | Robin Williams | Clinically NSFW |  |
| `persona_12` | Spin G | DJ | free | Donnell Rawlings | Lo-fi vibes, hi-fi insults |  |
| `persona_13` | Coach G | Motivational Speaker | free | Mo'Nique | Tough-love, X-rated |  |
| `persona_14` | Lord G | Royal | free | Joan Rivers | Pinkies up, knives out |  |
| `persona_15` | Thera G | Therapist | free | Maria Bamford | Therapy with claws |  |
| `persona_16` | Hype G | MC | free | Hannibal Buress | Maximum amp, max disrespect |  |
| `persona_17` | Crit G | Critic | free | Norm Macdonald | Pretentious, lethal, dirty |  |
| `persona_18` | Gainz G | Gym Bro | free | Joe Rogan-esque | All muscle, no foreplay |  |
| `persona_19` | Star G | Mystic Bard | free | Demetri Martin | Stars, sass, smut |  |
| `persona_20` | Slim G | Minimalist Comic | free | Mitch Hedberg | One sentence, full obituary |  |
| `persona_21` | Auntie Receipts | Petty Historian | free | Loni Love / Sherri Shepherd | Keeps the receipts, reads 'em out loud | ✔ |
| `persona_22` | Trucker Earl | Road Dog | free | Larry the Cable Guy / Jeff Foxworthy | 18 wheels, zero filter | ✔ |
| `persona_23` | Influencer Ivy | Clout Critic | free | Taylor Tomlinson / Bo Burnham | Link in bio, roast in comments | ✔ |
| `persona_24` | Uncle Grill | Cookout Commander | free | Bernie Mac / Cedric the Entertainer | Flips burgers, flips your self-esteem | ✔ |
| `persona_25` | Prof. Snark | Tenured Hater | free | Ricky Gervais / John Oliver | Peer-reviewed disrespect | ✔ |
| `persona_p1` | Big Tony | Heavyweight Roaster | premium | Ralphie May / Mike Epps | Heavyweight punchlines, zero filter |  |
| `persona_p2` | Gl1tchKing | Cyber Roastlord | premium | Michael Blaustein / Andrew Schulz | Terminally online, terminally dirty |  |
| `persona_p3` | Mama Sazón | Diva / Drama Roaster | premium | Sofía Vergara / George Lopez | Telenovela diva, kitchen knife mouth |  |
| `persona_p4` | The Reverend | Cold-Read Specialist | premium | D.C. Young Fly / Eddie Murphy | Ice-cold ghost-of-your-failures |  |
| `persona_p5` | King Lavish | Flex King | premium | Kevin Hart / Jamie Foxx | Designer flex, dollar-bin you |  |
| `persona_p6` | Duchess Venom | High-Society Assassin | premium | Joan Rivers / Lisa Lampanelli | Old money, fresh poison | ✔ |
| `persona_p7` | Sgt. Savage | Drill Instructor | premium | R. Lee Ermey / Bill Burr | Drop and give me your dignity | ✔ |
| `persona_p8` | Lil Glizzy | Chaos Hype Man | premium | Katt Williams / Lil Rel Howery | Hype man from hell | ✔ |
| `persona_p9` | Madame Oracle | Fortune Roaster | premium | Whoopi Goldberg / Margaret Cho | I've seen your future — it's embarrassing | ✔ |
| `persona_p10` | Coach Kowalski | Bitter Coach | premium | Norm Macdonald / Jim Gaffigan | Peaked in '94, still blowing the whistle | ✔ |
| `persona_p11` | Vegas Vinnie | Lounge Legend | premium | Don Rickles / Dean Martin | Rat Pack class, sewer-rat insults | ✔ |
| `persona_p12` | Dr. Nip Tuck | Cosmetic Critic | premium | Nikki Glaser / Anthony Jeselnik | Consultations are free, the truth isn't | ✔ |
| `persona_p13` | Ghost Gramps | Spectral Disappointment | premium | Rodney Dangerfield / Larry David | Died in '88, still disappointed | ✔ |
| `persona_p14` | Agent Zero | Covert Roaster | premium | Dave Chappelle / Keegan-Michael Key | Classified file, declassified shame | ✔ |
| `persona_p15` | Queen Clapback | Clapback Champion | premium | Leslie Jones / Tiffany Haddish | Ratio'd in real life | ✔ |

## Adding a persona
1. Append an object to `personas.json` with every field used by existing entries (incl. `tts_voice` one of alloy/echo/fable/onyx/nova/shimmer and `elevenlabs.voice_id`/`stability`). `tier`: `free` or `premium`.
2. Run `python scripts/generate_persona_portraits.py` — it creates any missing portrait.
3. Restart backend (persona file is read at startup). `pytest tests/test_personas_v6.py` validates completeness (update counts).
