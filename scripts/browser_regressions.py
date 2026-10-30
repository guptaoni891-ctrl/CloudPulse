"""Verify that an in-flight registration cannot expose a key after sign-out/re-login."""

import asyncio
import os
from pathlib import Path
from uuid import uuid4

import httpx
from playwright.async_api import async_playwright, expect


async def main():
    token = os.getenv("CLOUDPULSE_ADMIN_TOKEN")
    if not token:
        token = next(
            line.partition("=")[2]
            for line in Path(".env").read_text().splitlines()
            if line.startswith("CLOUDPULSE_ADMIN_TOKEN=")
        )
    base = os.getenv("CLOUDPULSE_SERVER", "http://127.0.0.1:8080")
    ready = asyncio.Event()
    released = asyncio.Event()
    delivered = asyncio.Event()
    registered = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=os.getenv("CHROMIUM_PATH", "/usr/bin/chromium"), args=["--no-sandbox"]
        )
        page = await browser.new_page()

        async def login():
            await page.get_by_label("Admin token").fill(token)
            await page.get_by_role("button", name="Open dashboard").click()
            await expect(
                page.get_by_role("heading", name="Infrastructure", exact=True)
            ).to_be_visible()

        async def delay_registration(route):
            if route.request.method != "POST":
                return await route.continue_()
            response = await route.fetch()
            assert response.status == 201
            registered.append((await response.json())["host"]["id"])
            ready.set()
            await released.wait()
            await route.fulfill(response=response)
            delivered.set()

        try:
            await page.goto(base)
            await login()
            await page.route("**/api/v1/hosts", delay_registration)
            await page.get_by_role("button", name="Register machine").click()
            await page.get_by_label("Machine name").fill("session-regression-" + uuid4().hex[:8])
            await page.get_by_role("button", name="Create agent key").click()
            await asyncio.wait_for(ready.wait(), 15)
            await page.get_by_role("button", name="Sign out").click()
            await login()
            released.set()
            await asyncio.wait_for(delivered.wait(), 15)
            await page.wait_for_load_state("networkidle")
            await expect(page.locator(".notice")).to_have_count(0)
            await expect(page.get_by_role("button", name="Refresh", exact=True)).to_be_enabled()
            print(
                "PASS: late registration response cannot restore an API key in a new browser session"
            )
        finally:
            released.set()
            await browser.close()
            async with httpx.AsyncClient(base_url=base, timeout=15) as client:
                for host_id in registered:
                    response = await client.patch(
                        f"/api/v1/hosts/{host_id}",
                        headers={"Authorization": "Bearer " + token},
                        json={"enabled": False},
                    )
                    response.raise_for_status()


if __name__ == "__main__":
    asyncio.run(main())
