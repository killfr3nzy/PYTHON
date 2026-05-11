"""Captcha-solver abstraction.

Provider-agnostic interface so the parser can swap between 2captcha,
Anti-Captcha, CapMonster, or a local mock without touching call sites.

Concrete providers implement `solve_recaptcha_v2` (sitekey + page_url ->
g-recaptcha-response token). Add more methods (hCaptcha, image, etc.)
when new fine sources need them.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import Protocol

import requests

from config import settings

logger = logging.getLogger(__name__)


class CaptchaError(RuntimeError):
    """Raised when the provider cannot deliver a token within the timeout."""


class CaptchaSolver(ABC):
    """Provider-agnostic captcha API."""

    name: str = "abstract"

    @abstractmethod
    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> str:
        """Return a g-recaptcha-response token for the given (sitekey, URL)."""

    def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "") -> str:
        """v3 returns a token with score; many sites only need the token.

        Default implementation falls back to v2-style call — providers that
        support v3 natively (2captcha, AntiCaptcha) override this.
        """
        return self.solve_recaptcha_v2(site_key, page_url)


class MockSolver(CaptchaSolver):
    """Dev/test stub: returns a constant string, never hits the network."""

    name = "mock"

    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> str:
        logger.info("MockSolver.solve_recaptcha_v2(%s, %s)", site_key, page_url)
        return "MOCK_TOKEN_" + site_key[:8]

    def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "") -> str:
        logger.info("MockSolver.solve_recaptcha_v3(%s, action=%s)", site_key, action)
        return "MOCK_V3_TOKEN_" + site_key[:8]


class TwoCaptchaSolver(CaptchaSolver):
    """https://2captcha.com — submit job, poll until ready."""

    name = "2captcha"
    base = "https://2captcha.com"

    def __init__(self, api_key: str, poll_interval: int = 5, timeout: int = 180):
        if not api_key:
            raise CaptchaError("2captcha api_key is empty")
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.timeout = timeout

    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> str:
        job_id = self._submit(
            method="userrecaptcha",
            googlekey=site_key,
            pageurl=page_url,
        )
        return self._poll(job_id)

    def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "") -> str:
        params = {
            "method": "userrecaptcha",
            "version": "v3",
            "googlekey": site_key,
            "pageurl": page_url,
            "min_score": "0.3",
        }
        if action:
            params["action"] = action
        job_id = self._submit(**params)
        return self._poll(job_id)

    def _submit(self, **kwargs) -> str:
        data = {"key": self.api_key, "json": 1, **kwargs}
        r = requests.post(f"{self.base}/in.php", data=data, timeout=15)
        r.raise_for_status()
        payload = r.json()
        if payload.get("status") != 1:
            raise CaptchaError(f"2captcha submit failed: {payload!r}")
        return payload["request"]

    def _poll(self, job_id: str) -> str:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            r = requests.get(
                f"{self.base}/res.php",
                params={"key": self.api_key, "action": "get", "id": job_id, "json": 1},
                timeout=15,
            )
            r.raise_for_status()
            payload = r.json()
            if payload.get("status") == 1:
                return payload["request"]
            if payload.get("request") not in ("CAPCHA_NOT_READY",):
                raise CaptchaError(f"2captcha poll failed: {payload!r}")
        raise CaptchaError(f"2captcha timeout after {self.timeout}s")


class AntiCaptchaSolver(CaptchaSolver):
    """https://anti-captcha.com — similar submit/poll flow."""

    name = "anti-captcha"
    base = "https://api.anti-captcha.com"

    def __init__(self, api_key: str, poll_interval: int = 5, timeout: int = 180):
        if not api_key:
            raise CaptchaError("anti-captcha api_key is empty")
        self.api_key = api_key
        self.poll_interval = poll_interval
        self.timeout = timeout

    def solve_recaptcha_v2(self, site_key: str, page_url: str) -> str:
        job_id = self._create_task({
            "type": "NoCaptchaTaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
        })
        return self._poll(job_id)

    def solve_recaptcha_v3(self, site_key: str, page_url: str, action: str = "") -> str:
        task = {
            "type": "RecaptchaV3TaskProxyless",
            "websiteURL": page_url,
            "websiteKey": site_key,
            "minScore": 0.3,
        }
        if action:
            task["pageAction"] = action
        job_id = self._create_task(task)
        return self._poll(job_id)

    def _create_task(self, task: dict) -> int:
        r = requests.post(
            f"{self.base}/createTask",
            json={"clientKey": self.api_key, "task": task},
            timeout=15,
        )
        r.raise_for_status()
        payload = r.json()
        if payload.get("errorId"):
            raise CaptchaError(f"anti-captcha createTask: {payload!r}")
        return payload["taskId"]

    def _poll(self, job_id: int) -> str:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            time.sleep(self.poll_interval)
            r = requests.post(
                f"{self.base}/getTaskResult",
                json={"clientKey": self.api_key, "taskId": job_id},
                timeout=15,
            )
            r.raise_for_status()
            payload = r.json()
            if payload.get("status") == "ready":
                return payload["solution"]["gRecaptchaResponse"]
            if payload.get("errorId"):
                raise CaptchaError(f"anti-captcha getTaskResult: {payload!r}")
        raise CaptchaError(f"anti-captcha timeout after {self.timeout}s")


_REGISTRY: dict[str, type[CaptchaSolver]] = {
    "mock": MockSolver,
    "2captcha": TwoCaptchaSolver,
    "anti-captcha": AntiCaptchaSolver,
}


def create_solver(provider: str | None = None, api_key: str | None = None) -> CaptchaSolver:
    """Build a solver from config defaults or explicit args.

    Falls back to MockSolver if provider is unknown OR api_key is missing
    for a real provider — surfaces a warning so the caller knows.
    """
    provider = (provider or settings.captcha_provider or "mock").lower()
    api_key = api_key or settings.captcha_api_key

    cls = _REGISTRY.get(provider)
    if cls is None:
        logger.warning("Unknown captcha provider %r, falling back to mock", provider)
        return MockSolver()

    if cls is MockSolver:
        return MockSolver()

    if not api_key:
        logger.warning("%s api_key is empty, falling back to mock", provider)
        return MockSolver()

    return cls(api_key=api_key)
