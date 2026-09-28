# Jarvis

One job: every morning, look at the Trading212 positions, what moved since the last
brief, and today's filtered news — then say in a few sentences what changed, what
matters, and what (if anything) needs attention.

No trading. No dashboard. No automation beyond a cron line.

The point is not the code. The point is step 4: **run it daily for two weeks and see
whether you act differently because of it.** If you don't, delete it.

---

## Setup (about ten minutes)

```bash
cd /path/to/legday-prototype
python3 -m venv .venv && source .venv/bin/activate
pip install -r jarvis/requirements.txt

cp jarvis/.env.example jarvis/.env
$EDITOR jarvis/.env
```

**Trading212 key** — in the app: Settings → API. It gives you an **API Key and an API
Secret**; Jarvis sends them as HTTP Basic auth. The key must carry the **`portfolio`**
and **`account`** scopes or you'll get `403 Scope( portfolio ) missing`. The API works
for Invest and Stocks ISA accounts only. Set `T212_ENV=demo` to point at the paper
account first.

**Finlight key** — the news feed. ⚠️ The key currently committed to the public
`aifa-news` repo is exposed; rotate it in Finlight before using it here, and keep the
new one only in `jarvis/.env`.

**Gmail** — `SMTP_PASS` must be an [App Password](https://myaccount.google.com/apppasswords),
not your account password. Google rejects the account password over SMTP.

Then check everything works before spending a cent:

```bash
python -m jarvis doctor
```

It prints what's configured, calls each API once, shows the live rate-limit headers,
and does **not** call Claude or send email.

## Daily use

```bash
python -m jarvis brief                 # fetch, think, email, save to state/briefs/
python -m jarvis brief --no-send       # same, printed instead of emailed
python -m jarvis brief --dry-run       # print exactly what Claude would be sent; no API call
python -m jarvis brief --offline       # run off bundled fixtures; no network at all
python -m jarvis brief --record        # also dump raw API payloads to fixtures/live/
python -m jarvis snapshot              # just record today's positions
```

Schedule it for weekday mornings:

```cron
30 7 * * 1-5 cd /path/to/legday-prototype && .venv/bin/python -m jarvis brief >> jarvis/state/cron.log 2>&1
```

On macOS, `cron` works but only runs when the machine is awake; a `launchd` agent with
`StartCalendarInterval` is the sturdier option if you want it to catch up after sleep.

## How it decides what to tell you

- **What changed** comes from snapshot diffing, not from the model. Each run writes
  `state/snapshots/YYYY-MM-DD.json` and compares against the previous file. Trading212
  has no "since yesterday" endpoint, so this is the only source of truth about change.
  **Day one has no diff and says so.**
- A **quantity change** is always reported — you made that decision.
- A **price move** is only reported if it clears `JARVIS_MOVE_PCT` (default 2%) *and*
  `JARVIS_MOVE_ABS` (default 50) — so a 5% wobble on a €30 position stays quiet.
- **News is filtered before the model sees it**: kept only if it names a holding or
  hits a thesis keyword (`jarvis/sources/finlight.py`). Typically ~10k input tokens
  instead of the whole feed.
- **`jarvis/profile.md` is the file you tune.** Risk tolerance, thesis, and the bar for
  being told anything. It goes into the system prompt verbatim. When the brief flags
  the wrong things, edit that file — not the code.

## Model and cost

`claude-fable-5-1`, effort `medium`, structured JSON output. Roughly 10–15k input and
~600 output tokens per run ≈ **$0.15/day**, so the two-week experiment costs about
**$2–3**. Override with `JARVIS_MODEL` / `JARVIS_EFFORT` (`claude-opus-5` is half the
input price if you want it cheaper).

Two deliberate choices worth knowing:

- **No prompt caching.** Cache entries live 5 minutes (1 hour at most). Running once a
  day means a cache write could never be read — it would add ~25% to input cost and
  return nothing. Revisit only if Jarvis starts running several times an hour.
- **Server-side fallbacks are on.** If a safety classifier declines a request, the API
  routes to another model rather than handing back an empty brief. The brief notes it
  when that happens.

## Not built yet

**Congressional / insider trades.** `jarvis/sources/congress.py` has the interface, the
normalizer, and a fixture — but no live provider. Every candidate host was unreachable
from the environment this was built in, so a parser written against one could not have
been run even once. Pick a provider (Quiver Quant with a key; disclosedcapitol.com or
congressinvests.com free tiers), run `python -m jarvis doctor --record`, and the
recorded payload turns the stub into about twenty lines. That's week-two work, after
you know whether the brief is worth reading at all.

## Tests

```bash
python -m unittest discover -s jarvis/tests -t .
```

59 tests, no network, no API key. They cover snapshot diffing (including the
first-run and below-threshold cases), Trading212 parsing against both the current and
the older payload shape, news filtering, the refusal and fallback paths of the Claude
call, and HTML escaping in the email.
