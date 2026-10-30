"""Optional real-browser smoke. Install requirements-browser.txt and Chromium first."""

import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import httpx
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
    machine_name = "review-linux-" + uuid4().hex[:8]
    page.get_by_label("Machine name").fill(machine_name)
    with page.expect_response(
        lambda response: (
            response.url.endswith("/api/v1/hosts") and response.request.method == "POST"
        )
    ) as event:
        page.get_by_role("button", name="Create agent key").click()
    registration = event.value.json()
    host_id = registration["host"]["id"]
    page.get_by_role("button", name="I have saved the key").click()
    for _ in range(3):
        subprocess.run(
            [sys.executable, "-m", "cloudpulse_agent.main", "--once"],
            env={
                **os.environ,
                "CLOUDPULSE_SERVER": base,
                "CLOUDPULSE_HOST_ID": host_id,
                "CLOUDPULSE_AGENT_KEY": registration["api_key"],
            },
            check=True,
        )
    # Read the actual PostgreSQL rows independently of the REST API.
    sql_check = """
import json, sys
from app.db import SessionLocal
from app.models import Metric
from sqlalchemy import select
with SessionLocal() as db:
    assert db.bind.dialect.name == 'postgresql'
    rows = db.scalars(select(Metric).where(Metric.host_id == sys.argv[1]).order_by(Metric.timestamp, Metric.id))
    print(json.dumps([{'id':m.id,'sample_id':m.sample_id,'cpu':m.cpu,'memory':m.memory,'disk':m.disk} for m in rows]))
"""
    result = subprocess.run(
        ["docker", "compose", "exec", "-T", "backend", "python", "-c", sql_check, host_id],
        check=True,
        capture_output=True,
        text=True,
    )
    db_rows = json.loads(result.stdout)
    assert len(db_rows) == 3
    with httpx.Client(base_url=base, timeout=15) as client:
        result = client.get(
            f"/api/v1/hosts/{host_id}/metrics", headers={"Authorization": "Bearer " + token}
        )
        result.raise_for_status()
        api_rows = result.json()
        assert [{key: row[key] for key in db_rows[0]} for row in api_rows] == db_rows
    page.get_by_role("button", name="Refresh", exact=True).click()
    page.get_by_role("button", name=machine_name).last.click()
    expect(page.get_by_role("heading", name="Resource utilization")).to_be_visible()
    expect(page.locator(".recharts-surface").first).to_be_visible()
    expect(page.locator("path.recharts-area-curve")).to_have_count(3)
    for field in ("cpu", "memory", "disk"):
        expect(page.locator(".metric-grid")).to_contain_text(f"{db_rows[-1][field]:.1f}%")
    page.get_by_label("History time range").select_option("6")
    page.get_by_label("Rule metric").select_option("disk")
    page.get_by_label("Threshold %").fill("0.1")
    page.get_by_role("button", name="Save rule").click()
    expect(page.locator(".rule").filter(has_text="DISK")).to_be_visible()
    # Exercise actual firing/recovery rendering, not just an empty event panel.
    for threshold in (None, "100"):
        if threshold is not None:
            page.get_by_label("Threshold %").fill(threshold)
            page.get_by_role("button", name="Save rule").click()
            expect(page.locator(".rule")).to_contain_text("100%")
        subprocess.run(
            [sys.executable, "-m", "cloudpulse_agent.main", "--once"],
            env={
                **os.environ,
                "CLOUDPULSE_SERVER": base,
                "CLOUDPULSE_HOST_ID": host_id,
                "CLOUDPULSE_AGENT_KEY": registration["api_key"],
            },
            check=True,
        )
    page.get_by_role("button", name="Refresh", exact=True).click()
    expect(page.locator(".event strong").filter(has_text="DISK threshold exceeded")).to_be_visible()
    expect(page.locator(".event strong").filter(has_text="DISK recovered")).to_be_visible()
    assert page.locator('[role="alert"]').count() == 0
    out = Path(os.getenv("CLOUDPULSE_SCREENSHOT_DIR", ".local/review-screenshots"))
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
    # A wrong token must never expose host data after sign-out.
    page.get_by_label("Admin token").fill("invalid-token-" + "x" * 32)
    page.get_by_role("button", name="Open dashboard").click()
    expect(page.get_by_role("alert")).to_contain_text("Authentication failed")
    assert page.locator(".host-link").count() == 0
    page.get_by_role("button", name="Sign in again").click()
    expect(page.get_by_label("Admin token")).to_be_visible()
    assert not errors, errors
    browser.close()
print(
    "PASS: agent CLI -> direct PostgreSQL rows -> REST equality -> rendered cards/3 chart series; login, rules, mobile, disable, sign-out and auth failure"
)
