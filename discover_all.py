"""Sweep every enabled Source and dump form structure + access status.

Usage on user's machine:

    docker compose exec bot bash -c "PLAYWRIGHT_HEADLESS=true python discover_all.py"

For each source, opens the URL once and writes a screenshot to
/tmp/discover_<key>.png. Final stdout is a compact summary table you can
paste back so the catalogue (sources.py) can be tightened to only the
cities that actually expose a working search form.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from sources import enabled_sources
from config import settings


JS_INSPECT = r"""
() => {
  const labelFor = (el) => {
    if (el.labels && el.labels.length) return el.labels[0].innerText.trim();
    const aria = el.getAttribute('aria-label');
    if (aria) return aria.trim();
    let parent = el.parentElement;
    for (let i = 0; i < 4 && parent; i++) {
      const text = parent.innerText.trim().slice(0, 100);
      if (text) return text;
      parent = parent.parentElement;
    }
    return null;
  };
  const fields = Array.from(document.querySelectorAll('input, select, textarea'))
    .filter((e) => e.type !== 'hidden')
    .map((e) => ({
      type: e.type || null,
      placeholder: e.placeholder || null,
      label: labelFor(e),
    }));
  const buttons = Array.from(document.querySelectorAll(
    'button, input[type=submit], input[type=button], [role=button]'
  )).map((e) => ((e.innerText || e.value || '').trim().slice(0, 60))).filter(Boolean);
  return {
    title: document.title.slice(0, 100),
    finalUrl: location.href,
    htmlLen: document.documentElement.outerHTML.length,
    bodyText: (document.body ? document.body.innerText : '').slice(0, 400),
    fieldCount: fields.length,
    fields,
    buttonCount: buttons.length,
    buttons: buttons.slice(0, 10),
    captcha_sitekeys: Array.from(document.querySelectorAll('[data-sitekey]'))
      .map((e) => e.getAttribute('data-sitekey')),
  };
}
"""


def classify(payload: dict[str, Any]) -> str:
    title = payload.get("title", "")
    body = payload.get("bodyText", "")
    if "Access Denied" in title or "Access Denied" in body or "edgesuite" in body:
        return "blocked"
    if payload.get("htmlLen", 0) < 1000 and not payload.get("fields"):
        return "empty"
    if payload.get("fieldCount", 0) >= 2:
        return "form-found"
    if payload.get("buttonCount", 0) > 0:
        return "landing"
    return "unknown"


def main() -> int:
    from playwright.sync_api import sync_playwright

    headless = settings.playwright_headless
    sources = enabled_sources()
    print(f"▸ Sweeping {len(sources)} sources (headless={headless})\n", file=sys.stderr)

    findings: dict[str, dict] = {}

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

        for source in sources:
            print(f"▸ {source.name_ru:20} → {source.url}", file=sys.stderr)
            page = context.new_page()
            try:
                response = page.goto(source.url, wait_until="domcontentloaded", timeout=20_000)
                try:
                    page.wait_for_load_state("networkidle", timeout=8_000)
                except Exception:
                    pass
                page.wait_for_timeout(2_000)

                screenshot = f"/tmp/discover_{source.key}.png"
                try:
                    page.screenshot(path=screenshot, full_page=True)
                except Exception:
                    screenshot = None

                data = page.evaluate(JS_INSPECT)
                data["status"] = response.status if response else None
                data["verdict"] = classify(data)
                data["screenshot"] = screenshot
                findings[source.key] = data

                print(
                    f"  status={data['status']}  verdict={data['verdict']}  "
                    f"fields={data['fieldCount']}  title={data['title'][:50]!r}",
                    file=sys.stderr,
                )
            except Exception as exc:
                findings[source.key] = {"error": str(exc), "verdict": "error"}
                print(f"  ERROR: {exc}", file=sys.stderr)
            finally:
                page.close()

        browser.close()

    # Summary table on stderr
    print("\n▸ Summary:\n", file=sys.stderr)
    print(f"{'KEY':15} {'VERDICT':12} {'FIELDS':>6}  TITLE", file=sys.stderr)
    print("-" * 80, file=sys.stderr)
    for key, data in findings.items():
        verdict = data.get("verdict", "?")
        fields = data.get("fieldCount", "—")
        title = (data.get("title") or "")[:50]
        print(f"{key:15} {verdict:12} {str(fields):>6}  {title}", file=sys.stderr)

    # Full JSON on stdout — paste back to share
    print(json.dumps(findings, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
