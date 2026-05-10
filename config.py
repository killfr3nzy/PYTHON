"""Application configuration loaded from environment variables.

Set these in your shell or in a local .env file (which is git-ignored):

    TG_BOT_TOKEN=...                # Telegram bot token from @BotFather
    ANTHROPIC_API_KEY=...           # Optional. If empty, falls back to templates.
    LLM_MODE=auto                   # auto | claude | template
    CLAUDE_MODEL=claude-sonnet-4-6
    PARSER_MODE=mock                # mock | live
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

    @property
    def use_claude(self) -> bool:
        if self.llm_mode == "claude":
            return True
        if self.llm_mode == "template":
            return False
        return bool(self.anthropic_api_key)


settings = Settings(
    tg_bot_token=os.getenv("TG_BOT_TOKEN", ""),
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
    llm_mode=os.getenv("LLM_MODE", "auto").lower(),
    claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
    parser_mode=os.getenv("PARSER_MODE", "mock").lower(),
)
