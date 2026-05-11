"""Discover the actual structure of the configured live page.

Run this ONCE on your local machine after configuring MOT_LOOKUP_URL in .env:

    python discover.py

Opens the page in a visible browser (headed mode), waits for everything to
render, then dumps:
  - all input fields with their resolved labels, placeholders, role names
  - all buttons / clickable submit elements
  - whether any captcha widget is present

Use the output to verify or tune the constants in parser.py:
  LIVE_FIELDS, LIVE_SUBMIT_TEXTS
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
    // Nearest preceding visible text node within the same row/container.
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
  })).filter((b) => b.text);
  const captcha = {
    recaptcha_sitekeys: Array.from(document.querySelectorAll('[data-sitekey]'))
      .map((e) => e.getAttribute('data-sitekey')),
    hcaptcha: document.querySelectorAll('[data-hcaptcha-sitekey]').length > 0,
    turnstile: document.querySelectorAll('.cf-turnstile').length > 0,
  };
  return {url: location.href, fields, buttons, captcha};
}
"""


def main() -> int:
    from playwright.sync_api import sync_playwright

    url = settings.mot_lookup_url
    print(f"▸ Opening {url}", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, args=["--lang=he-IL"])
        context = browser.new_context(locale="he-IL")
        page = context.new_page()
        page.goto(url, wait_until="networkidle", timeout=30_000)
        page.wait_for_timeout(2_000)
        result = page.evaluate(JS_INSPECT)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        print(
            "\n▸ Browser stays open for inspection. Press Enter to close.",
            file=sys.stderr,
        )
        input()
        browser.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
