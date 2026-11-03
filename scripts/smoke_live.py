"""Smoke test for a deployed PropTalk: open it cold and ask the first example.

    python scripts/smoke_live.py <url> [--mobile] [--skip-trust-check] [--screenshot PATH]

Exits 0 on pass, 1 on failure (printing the failed step). Playwright is a
dev-only tool and is imported inside main(), so pytest never needs it:

    pip install playwright && python -m playwright install chromium
    (a preinstalled Chromium at /opt/pw-browsers/chromium is used as a fallback)

Steps: open the URL; wake a sleeping app; find the frame that holds the app
(Community Cloud may serve it inside an iframe); click the first example; wait
for the chart, then open the Table tab and wait for the table; check there is no
leftover 'Done in ...' widget; check the trust panel; take a screenshot.
"""

import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

import config  # noqa: E402

APP_TIMEOUT_MS = 120_000  # also covers a sleeping app waking up
ANSWER_TIMEOUT_MS = 60_000
TRUST_TEXT = "How this answer was produced"
CHROMIUM_FALLBACK = "/opt/pw-browsers/chromium"
MOBILE_VIEWPORT = {"width": 390, "height": 844}


class SmokeFailure(Exception):
    """A named step failed."""

    def __init__(self, step: str, detail: str = "") -> None:
        super().__init__(f"{step}: {detail}" if detail else step)


def _launch(playwright):
    try:
        return playwright.chromium.launch()
    except Exception:
        if os.path.exists(CHROMIUM_FALLBACK):
            return playwright.chromium.launch(executable_path=CHROMIUM_FALLBACK, args=["--no-sandbox"])
        raise


def _find_app_frame(page, timeout_ms: int):
    """The frame that contains the Streamlit app: the page itself, or an iframe."""
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for frame in page.frames:
            try:
                if frame.locator('[data-testid="stApp"]').count():
                    return frame
            except Exception:
                continue  # a frame that is mid-navigation
        page.wait_for_timeout(500)
    raise SmokeFailure("find the app frame", f"no stApp in any frame after {timeout_ms // 1000}s")


def run(url: str, mobile: bool, check_trust: bool, screenshot: str) -> None:
    """Raises SmokeFailure naming the step that failed."""
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import sync_playwright

    example = config.TABLE_REGISTRY[0].example_questions[0]
    with sync_playwright() as p:
        browser = _launch(p)
        try:
            context = browser.new_context(
                viewport=MOBILE_VIEWPORT if mobile else {"width": 1280, "height": 900},
                device_scale_factor=2 if mobile else 1,
                is_mobile=mobile, has_touch=mobile,
            )
            page = context.new_page()
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            except PlaywrightError as exc:
                raise SmokeFailure("open the URL", str(exc).splitlines()[0]) from exc

            wake = page.get_by_role("button", name=re.compile("get this app back up", re.I))
            try:
                wake.wait_for(state="visible", timeout=5_000)
            except PlaywrightError:
                pass  # not sleeping
            else:
                wake.click()

            frame = _find_app_frame(page, APP_TIMEOUT_MS)

            button = frame.get_by_role("button", name=example).first
            try:
                button.wait_for(state="visible", timeout=30_000)
            except PlaywrightError as exc:
                raise SmokeFailure("find the first example button", example) from exc
            button.click()

            def _wait(selector: str, what: str) -> None:
                try:
                    frame.locator(selector).first.wait_for(state="visible", timeout=ANSWER_TIMEOUT_MS)
                except PlaywrightError as exc:
                    shown = frame.locator('[data-testid="stException"], [data-testid="stAlert"]').all_inner_texts()
                    raise SmokeFailure(f"wait for the {what}", f"page shows: {shown[:2]}") from exc

            _wait(".js-plotly-plot", "chart")  # the Chart tab is first and open
            # The table sits in its own tab; Streamlit does not show an inactive tab's content.
            try:
                frame.get_by_role("tab", name=re.compile(r"^Table")).click(timeout=15_000)
            except PlaywrightError as exc:
                raise SmokeFailure("open the Table tab", "no tab named 'Table...' (is the app running an older version?)") from exc
            _wait('[data-testid="stDataFrame"]', "table")

            if frame.get_by_text(re.compile(r"^Done in \d")).count():
                raise SmokeFailure("no leftover progress widget", "found a 'Done in ...' element")

            if frame.locator('[data-testid="stException"]').count():
                raise SmokeFailure("no exception on the page", frame.locator('[data-testid="stException"]').first.inner_text())

            if check_trust:
                try:
                    frame.get_by_text(TRUST_TEXT).first.wait_for(state="visible", timeout=10_000)
                except PlaywrightError as exc:
                    raise SmokeFailure("trust panel", f"'{TRUST_TEXT}' not found") from exc

            os.makedirs(os.path.dirname(os.path.abspath(screenshot)), exist_ok=True)
            page.screenshot(path=screenshot, full_page=True)
        finally:
            browser.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("url")
    parser.add_argument("--mobile", action="store_true", help="390x844 touch viewport")
    parser.add_argument("--skip-trust-check", action="store_true",
                        help="do not require the 'How this answer was produced' panel")
    parser.add_argument("--screenshot", default=None, help="where to save the screenshot")
    args = parser.parse_args(argv)
    shot = args.screenshot or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, ".mockups",
        "smoke_mobile.png" if args.mobile else "smoke_desktop.png")
    try:
        run(args.url, args.mobile, not args.skip_trust_check, shot)
    except SmokeFailure as exc:
        print(f"FAIL at step: {exc}")
        return 1
    print(f"PASS ({'mobile' if args.mobile else 'desktop'}); screenshot: {os.path.normpath(shot)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
