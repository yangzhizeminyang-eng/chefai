#!/usr/bin/env python3
"""Capture screenshots of every slide of the HTML PPT (Windows-friendly)."""
import os
import sys

from playwright.sync_api import sync_playwright

URL = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:5173"
OUT = sys.argv[2] if len(sys.argv) > 2 else "public/assets/images/posters/pages"
TOTAL = int(sys.argv[3]) if len(sys.argv) > 3 else 20
CHANNEL = sys.argv[4] if len(sys.argv) > 4 else "chrome"

os.makedirs(OUT, exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel=CHANNEL)
    ctx = browser.new_context(viewport={"width": 1560, "height": 900}, device_scale_factor=2)
    page = ctx.new_page()
    for i in range(1, TOTAL + 1):
        page.goto(f"{URL}?page={i}", wait_until="domcontentloaded", timeout=60000)
        page.add_style_tag(
            content=".nav-btn,.page-indicator,.progress-bar,.keyboard-hint{display:none !important;}"
        )
        try:
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception:
            pass
        page.wait_for_timeout(1200)
        page.locator("#ppt-viewport").screenshot(path=os.path.join(OUT, f"page-{i}.png"))
        print(f"captured page-{i}.png", flush=True)
    browser.close()
print("done")
