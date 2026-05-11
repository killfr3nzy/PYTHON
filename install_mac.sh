#!/usr/bin/env bash
#
# One-shot installer for macOS. Usage:
#
#   bash <(curl -fsSL <raw-url>/install_mac.sh)
#
# Or just download the file and run `bash install_mac.sh`.
#
# What it does:
#   1. Verifies Homebrew (offers to install if missing).
#   2. Verifies Docker (installs colima + docker CLI via brew, or
#      tells you to install Docker Desktop).
#   3. Clones the repo if you are not already in it.
#   4. Creates .env from .env.example and prompts for any missing
#      secrets interactively.
#   5. Builds the Docker image and starts the bot in detached mode.
#   6. Tails the logs so you can see it come up.

set -euo pipefail

REPO_URL="https://github.com/killfr3nzy/python.git"
BRANCH="claude/traffic-fine-appeals-bHjTK"
REPO_DIR="PYTHON"

red()    { printf "\033[31m%s\033[0m\n" "$*"; }
green()  { printf "\033[32m%s\033[0m\n" "$*"; }
yellow() { printf "\033[33m%s\033[0m\n" "$*"; }
blue()   { printf "\033[34m%s\033[0m\n" "$*"; }

require_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        return 1
    fi
}

# ---------------------------------------------------------------------------
# 1. Homebrew
# ---------------------------------------------------------------------------
blue "▸ Checking Homebrew..."
if ! require_cmd brew; then
    yellow "  Homebrew not found. Install it now? (y/N)"
    read -r answer
    if [[ "$answer" =~ ^[yY]$ ]]; then
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    else
        red "  Aborting. Install Homebrew from https://brew.sh and re-run."
        exit 1
    fi
fi
green "  ✓ brew $(brew --version | head -1 | awk '{print $2}')"

# ---------------------------------------------------------------------------
# 2. Docker (Desktop OR colima)
# ---------------------------------------------------------------------------
blue "▸ Checking Docker..."
if require_cmd docker && docker info >/dev/null 2>&1; then
    green "  ✓ Docker daemon already running"
else
    yellow "  Docker is missing or not running."
    yellow "  Install colima (free, lightweight) + docker CLI now? (y/N)"
    read -r answer
    if [[ "$answer" =~ ^[yY]$ ]]; then
        brew install colima docker docker-compose
        colima start --cpu 2 --memory 4 --disk 20
    else
        red "  Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and re-run."
        exit 1
    fi
fi
green "  ✓ docker $(docker --version | awk '{print $3}' | tr -d ',')"

# ---------------------------------------------------------------------------
# 3. Clone or update the repo
# ---------------------------------------------------------------------------
blue "▸ Repository..."
if [[ -d "$REPO_DIR/.git" ]]; then
    green "  ✓ repo exists; pulling latest"
    git -C "$REPO_DIR" fetch origin
    git -C "$REPO_DIR" checkout "$BRANCH"
    git -C "$REPO_DIR" pull origin "$BRANCH"
else
    yellow "  Cloning $REPO_URL ..."
    git clone "$REPO_URL" "$REPO_DIR"
    git -C "$REPO_DIR" checkout "$BRANCH"
fi
cd "$REPO_DIR"
green "  ✓ on branch $(git rev-parse --abbrev-ref HEAD)"

# ---------------------------------------------------------------------------
# 4. .env setup
# ---------------------------------------------------------------------------
blue "▸ Configuring .env ..."
if [[ ! -f .env ]]; then
    cp .env.example .env
    yellow "  Created .env from template."
fi

prompt_if_empty() {
    local key="$1"
    local label="$2"
    local current
    current=$(grep "^${key}=" .env | cut -d= -f2- || true)
    if [[ -z "$current" ]]; then
        printf "  %s: " "$label"
        read -r value
        if [[ -n "$value" ]]; then
            # macOS sed needs an empty backup extension argument
            sed -i '' "s|^${key}=.*|${key}=${value}|" .env
        fi
    fi
}

prompt_if_empty TG_BOT_TOKEN          "Telegram bot token"
prompt_if_empty ANTHROPIC_API_KEY     "Anthropic API key (or leave empty for templates)"
prompt_if_empty CAPTCHA_API_KEY       "2captcha API key"
prompt_if_empty MOT_SITE_KEY          "MOT_SITE_KEY (data-sitekey from jerinfogen page)"

green "  ✓ .env populated"

# ---------------------------------------------------------------------------
# 5. Build and start
# ---------------------------------------------------------------------------
blue "▸ Building Docker image (first time ≈5 min)..."
docker compose build

blue "▸ Starting bot..."
docker compose up -d

green "  ✓ Container is up"
blue "▸ Tailing logs (Ctrl+C to detach, container keeps running)"
sleep 1
docker compose logs -f bot
