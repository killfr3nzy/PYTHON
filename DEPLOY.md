# Deploy on your own hardware (Docker)

The image is based on Microsoft's official Playwright image, so Chromium
and all its system libraries come pre-installed — no host setup beyond
Docker itself.

## Requirements

- Docker 20.10+ and docker-compose v2 on Linux, macOS, or Windows (WSL2).
- ~2 GB RAM free for the container.
- Outbound internet (gov.il, api.telegram.org, api.anthropic.com, 2captcha.com).

## First run

```bash
git clone <repo-url>
cd PYTHON
git checkout claude/traffic-fine-appeals-bHjTK

# Copy the template and fill in your secrets:
cp .env.example .env
$EDITOR .env

docker compose up --build -d
docker compose logs -f bot      # follow output
```

The first build pulls ~1.5 GB Playwright base image (one-time).
Subsequent rebuilds are fast — only `pip install` and the COPY layer.

## Stop / restart / update

```bash
docker compose down             # stop and remove container
docker compose up -d            # start in background
docker compose restart bot      # restart after .env change
git pull && docker compose up --build -d   # apply code updates
```

## Logs and shell

```bash
docker compose logs --tail=100 bot
docker compose exec bot bash    # interactive shell inside the container
docker compose exec bot python -c "from parser import lookup; print(lookup('39477602', israeli_id='323428052', fine_number='123').error)"
```

## File layout

```
.
├── bot.py              # Telegram entrypoint
├── parser.py           # mock + Playwright live mode
├── captcha.py          # 2captcha / anti-captcha / mock
├── llm.py              # Claude + template letter generator
├── templates.py        # Hebrew letter templates and analyser
├── config.py           # env loader
├── requirements.txt
├── Dockerfile          # built on playwright:v1.49.0-jammy
├── docker-compose.yml  # one-service stack with shm_size=1gb
├── .dockerignore       # keeps .env, .git, docs out of the image
└── .env                # YOUR secrets — never commit
```

## Common issues

**`TG_BOT_TOKEN is not set`** — your `.env` is empty or not mounted.
Check `docker compose config` shows the file under `env_file:`.

**Captcha calls hang for 3 minutes** — 2captcha is overloaded or the
sitekey is wrong. Watch their dashboard: https://2captcha.com/enterpage

**Chromium crashes inside the container** — bump `shm_size` higher in
`docker-compose.yml`. Default `/dev/shm` (64 MB) is too small for
Playwright; we already raise it to 1 GB.

**Bot stops receiving updates** — Telegram drops long-polling sessions
periodically. `restart: unless-stopped` brings the container back; if
restart loops, check `docker compose logs` for stack traces.

## Resource use

Idle: ~150 MB RAM, <1 % CPU. Each live lookup spikes briefly to ~400 MB
while Chromium is open. Cost of running on a Raspberry Pi 4 (4 GB): zero
beyond the electricity bill.
