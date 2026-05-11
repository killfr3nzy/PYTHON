"""Discover the actual structure of the configured live page.

Run on the user's machine (NOT inside this sandbox — outbound is blocked):

    docker compose exec bot bash -c \\
      "MOT_LOOKUP_URL='https://...' PLAYWRIGHT_HEADLESS=true python discover.py"

Dumps JSON with everything we can detect on the page and saves a screenshot
to /tmp/discover.png inside the container (copy out with `docker compose cp`).
"""

from __future__ import annotations

import json
import sys

from config import settings


JS_INSPECT = r"""
() => {
  const labelFor = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    const aribby = el.getAttribute('aria-labelledby');
    if (aribby) {
      const ref = document.getElementById(aribby);
      if (ref) return ref.innerText.trim();
    }
    let parent = el.parentElement;
    for (let i = 0; i < 4 && parent; i++) {
      const text = parent.innerText.trim().slice(0, 120);
      if (text) return text;
      parent = parent.parentElement;
    }
    return null;
  };
  const fields = Array.from(document.querySelectorAll('input, select, textarea'))
    .filter((e) => e.type !== 'hidden')
    .map((e, i) => ({
      idx: i,
      tag: e.tagName,
      type: e.type || null,
      name: e.name || null,
      id: e.id || null,
      placeholder: e.placeholder || null,
      ariaLabel: e.getAttribute('aria-label') || null,
      label: labelFor(e),
    }));
  const buttons = Array.from(document.querySelectorAll(
    'button, input[type=submit], input[type=button], [role=button], a[href]'
  )).map((e) => ({
    tag: e.tagName,
    text: (e.innerText || e.value || '').trim().slice(0, 80),
    role: e.getAttribute('role') || null,
    type: e.type || null,
    href: e.getAttribute('href') || null,
  })).filter((b) => b.text || b.href);
  const captcha = {
    recaptcha_sitekeys: Array.from(document.querySelectorAll('[data-sitekey]'))
      .map((e) => e.getAttribute('data-sitekey')),
    hcaptcha: document.querySelectorAll('[data-hcaptcha-sitekey]').length > 0,
    turnstile: document.querySelectorAll('.cf-turnstile').length > 0,
  };
  const iframes = Array.from(document.querySelectorAll('iframe')).map((f) => ({
    src: f.src || null,
    name: f.name || null,
  }));
  return {
    title: document.title,
    finalUrl: location.href,
    htmlLen: document.documentElement.outerHTML.length,
    bodyText: (document.body ? document.body.innerText : '').slice(0, 800),
    fields,
    buttons,
    iframes,
    captcha,
  };
}
"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    url = settings.mot_lookup_url
    headless = settings.playwright_headless
    print(f"▸ Opening {url} (headless={headless})", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless, args=["--lang=he-IL"])
        context = browser.new_context(
            locale="he-IL",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        response = page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        print(f"▸ HTTP {response.status if response else '?'} → {page.url}", file=sys.stderr)

        # Wait for likely-rendered content. networkidle may never fire on SPAs
        # that keep polling, so fall back to a hard timeout.
        try:
            page.wait_for_load_state("networkidle", timeout=10_000)
        except Exception:
            print("▸ networkidle timed out — continuing anyway", file=sys.stderr)
        page.wait_for_timeout(3_000)

        screenshot = "/tmp/discover.png"
        page.screenshot(path=screenshot, full_page=True)
        print(f"▸ Screenshot saved to {screenshot} inside the container.", file=sys.stderr)
        print(f"  Copy out: docker compose cp bot:{screenshot} ./discover.png", file=sys.stderr)

        result = page.evaluate(JS_INSPECT)
        print(json.dumps(result, ensure_ascii=False, indent=2))

        if not headless:
            print("\n▸ Press Enter to close.", file=sys.stderr)
            input()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
