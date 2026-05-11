# Live run — checklist

This sandbox has no outbound internet (`host_not_allowed` for gov.il,
2captcha.com, even google.com), so the live test must run on your own
machine. Everything else is wired up.

The bot queries all enabled municipal portals listed in `sources.py`
(Jerusalem, Tel Aviv-Yafo, Haifa, Beer Sheva, Rishon LeZion, Netanya,
Petah Tikva, Holon, and the national police). A failure in one source
is recorded as a per-city warning but does not stop the rest.

## 1. Pull and install

```bash
git pull origin claude/traffic-fine-appeals-bHjTK
pip install -r requirements.txt
playwright install chromium
```

## 2. Configure `.env`

Already written by Claude with the credentials you provided:

```
TG_BOT_TOKEN=...
ANTHROPIC_API_KEY=...
CAPTCHA_API_KEY=f8f3ed2f123a584e8cab8845c2974a17
PARSER_MODE=live
CAPTCHA_PROVIDER=2captcha
MOT_LOOKUP_URL=https://jerinfogen.jerusalem.muni.il/findreport/default.aspx
MOT_SITE_KEY=    # <-- FILL THIS IN, see step 3
PLAYWRIGHT_HEADLESS=false   # leave false for debugging
```

## 3. Captcha (often not needed)

Jerusalem's portal does not use reCAPTCHA — verified live. Leave
`MOT_SITE_KEY` empty in `.env` and the solver step is skipped.

If a different city DOES use reCAPTCHA, add its sitekey to that source
in `sources.py:ALL_SOURCES` (`site_key` field), not to `.env`.

## 4. Verify form structure (per source, 30 sec)

Each Source in `sources.py` lists Hebrew labels Playwright will use to
find the input fields. To verify any one of them against the live page:

```bash
python discover.py
```

Opens the configured `MOT_LOOKUP_URL` in a visible browser and prints
JSON with every input field, its label, role, and placeholder. Use the
output to update `fine_labels`/`plate_labels`/`id_labels` in `sources.py`
if the actual page uses different wording.

## 5. Test from CLI (before involving the bot)

```bash
python -c "
from parser import lookup
r = lookup('39477602', israeli_id='323428052', fine_number='<KNOWN_FINE_NO>')
print('error:', r.error)
print('fines:', len(r.fines))
for f in r.fines:
    print(' ', f.fine_id, f.violation, f.amount_ils, '₪')
"
```

You will need ONE known fine number — from an SMS, paper ticket, or
email. Jerusalem's portal does not return anything without it; this is
intentional privacy protection by the municipality.

## 6. If reCAPTCHA is missing or different

The Jerusalem portal may use:

* No captcha at all → leave `MOT_SITE_KEY` empty; comment out the
  `solver.solve_recaptcha_v2(...)` block in `parser.py:_lookup_live`.
* hCaptcha → extend `captcha.py` with a `solve_hcaptcha(site_key, url)`
  method. 2captcha supports it via `method=hcaptcha`.
* reCAPTCHA v3 → requires `score` and `action`. 2captcha supports it
  via `method=userrecaptcha, version=v3`.

## 7. Run the bot once selectors and captcha are confirmed

```bash
python bot.py
```

In Telegram:
1. `/start`
2. Send plate `39477602`
3. Send ID `323428052`
4. Send any known fine number
5. Receive list of all fines + Hebrew appeal letters

## 8. Switching to Tel Aviv as the source

Set in `.env`:
```
MOT_LOOKUP_URL=https://tlvpay.tel-aviv.gov.il/he/service/1/1
MOT_SITE_KEY=<sitekey from Tel Aviv page>
```
And update `LIVE_SELECTORS` to match the Tel Aviv form (different field
names). Same captcha solver works.

## Known limitations

* **No "all fines from one plate" API exists in Israel.** Both gov.il
  police and municipal portals require at least one fine number as a
  privacy gate. This is why the bot now asks for it.
* **Per-municipality fragmentation.** Jerusalem and Tel Aviv have
  separate portals with separate sitekeys and selectors. National
  speeding fines from `gov.il/police_fine_payment` require the fine
  number too and have their own form.
* **No SSL CA in this sandbox.** `aiohttp` cannot reach
  `api.telegram.org` from here — but it works on any normal machine.

## Files involved

| File | Purpose |
|---|---|
| `bot.py` | Telegram interaction, three-step FSM |
| `parser.py` | Mock samples + Playwright live flow |
| `captcha.py` | 2captcha / anti-captcha / mock solver |
| `llm.py` | Claude + template letter generator |
| `templates.py` | Rule-based analyser + Hebrew letter templates |
| `config.py` | env loading |
| `.env` | local secrets (gitignored) |
