"""Optional real-browser smoke. Install requirements-browser.txt and Chromium first."""

import os
from pathlib import Path

import httpx
from cloudpulse_agent.main import collect
from playwright.sync_api import expect, sync_playwright

base = os.getenv("CLOUDPULSE_SERVER", "http://127.0.0.1:8080")
token = os.getenv("CLOUDPULSE_ADMIN_TOKEN")
if not token:
    for line in Path(".env").read_text().splitlines():
        if line.startswith("CLOUDPULSE_ADMIN_TOKEN="):
            token = line.partition("=")[2]
if not token:
    raise SystemExit("Admin token is required")

errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(
        executable_path=os.getenv("CHROMIUM_PATH", "/usr/bin/chromium"), args=["--no-sandbox"]
    )
    page = browser.new_page(viewport={"width": 1440, "height": 1050})
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(base)
    page.get_by_label("Admin token").fill(token)
    page.get_by_role("button", name="Open dashboard").click()
    expect(page.get_by_role("heading", name="Infrastructure", exact=True)).to_be_visible()
    page.get_by_role("button", name="Register machine").click()
    page.get_by_label("Machine name").fill("linux-dev-machine")
    with page.expect_response(
        lambda response: (
            response.url.endswith("/api/v1/hosts") and response.request.method == "POST"
        )
    ) as event:
        page.get_by_role("button", name="Create agent key").click()
    registration = event.value.json()
    host_id = registration["host"]["id"]
    page.get_by_role("button", name="I have saved the key").click()
    with httpx.Client(base_url=base, timeout=15) as client:
        for _ in range(3):
            result = client.post(
                f"/api/v1/hosts/{host_id}/metrics",
                headers={"X-API-Key": registration["api_key"]},
                json=collect(Path.home().anchor),
            )
            result.raise_for_status()
    page.get_by_role("button", name="Refresh", exact=True).click()
    page.get_by_role("button", name="linux-dev-machine").last.click()
    expect(page.get_by_role("heading", name="Resource utilization")).to_be_visible()
    expect(page.locator(".recharts-surface").first).to_be_visible()
    page.get_by_label("History time range").select_option("6")
    page.get_by_label("Rule metric").select_option("disk")
    page.get_by_label("Threshold %").fill("80")
    page.get_by_role("button", name="Save rule").click()
    expect(page.locator(".rule").filter(has_text="DISK")).to_be_visible()
    assert page.locator('[role="alert"]').count() == 0
    out = Path("docs/screenshots")
    out.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(out / "dashboard.png"), full_page=True)
    page.set_viewport_size({"width": 390, "height": 844})
    expect(page.get_by_role("heading", name="Resource utilization")).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.screenshot(path=str(out / "mobile.png"), full_page=True)
    page.get_by_role("button", name="Disable agent").click()
    expect(page.get_by_role("button", name="Enable agent")).to_be_visible()
    page.get_by_role("button", name="Sign out").click()
    expect(page.get_by_label("Admin token")).to_be_visible()
    assert not page.evaluate("localStorage.length || sessionStorage.length")
    assert not errors, errors
    browser.close()
print(
    "PASS: browser login, registration, real charts, range, rule edit, mobile layout, disable and sign-out"
)
