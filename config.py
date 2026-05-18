"""Application configuration loaded from environment variables.

Set these in your shell or in a local .env file (which is git-ignored):

    TG_BOT_TOKEN=...                # Telegram bot token from @BotFather
    ANTHROPIC_API_KEY=...           # Optional. If empty, falls back to templates.
    LLM_MODE=auto                   # auto | claude | template
    CLAUDE_MODEL=claude-sonnet-4-6
    PARSER_MODE=mock                # mock | live
    CAPTCHA_PROVIDER=2captcha       # mock | 2captcha | anti-captcha
    CAPTCHA_API_KEY=...             # required when PARSER_MODE=live
    MOT_LOOKUP_URL=https://www.gov.il/he/service/check-traffic-tickets
    MOT_SITE_KEY=                   # reCAPTCHA v2 sitekey of the lookup page
    PLAYWRIGHT_HEADLESS=true        # set to false to watch the browser
"""

import os
from dataclasses import dataclass

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


@dataclass(frozen=True)
class Settings:
    tg_bot_token: str
    anthropic_api_key: str
    llm_mode: str
    claude_model: str
    parser_mode: str
    captcha_provider: str
    captcha_api_key: str
    mot_lookup_url: str
    mot_site_key: str
    playwright_headless: bool

    @property
    def use_claude(self) -> bool:
        if self.llm_mode == "claude":
            return True
        if self.llm_mode == "template":
            return False
        return bool(self.anthropic_api_key)


def _bool(value: str, default: bool = True) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


settings = Settings(
    tg_bot_token=os.getenv("TG_BOT_TOKEN", ""),
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    llm_mode=os.getenv("LLM_MODE", "auto").lower(),
    claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
    parser_mode=os.getenv("PARSER_MODE", "mock").lower(),
    captcha_provider=os.getenv("CAPTCHA_PROVIDER", "mock").lower(),
    captcha_api_key=os.getenv("CAPTCHA_API_KEY", ""),
    mot_lookup_url=os.getenv("MOT_LOOKUP_URL", "https://www.gov.il/he/service/check-traffic-tickets"),
    mot_site_key=os.getenv("MOT_SITE_KEY", ""),
    playwright_headless=_bool(os.getenv("PLAYWRIGHT_HEADLESS", "true"), default=True),
)
