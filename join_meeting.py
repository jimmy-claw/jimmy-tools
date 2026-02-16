#!/usr/bin/env python3
"""Launch browser and join a video meeting (Google Meet or Jitsi)."""

import asyncio
import sys
import os
from urllib.parse import urlparse
from playwright.async_api import async_playwright
import config


def detect_platform(url: str) -> str:
    """Detect meeting platform from URL."""
    host = urlparse(url).hostname or ""
    if "meet.google.com" in host:
        return "google-meet"
    if "jit.si" in host or "jitsi" in host:
        return "jitsi"
    if "zoom.us" in host:
        return "zoom"
    return "unknown"


async def join_jitsi(page, url: str):
    """Join a Jitsi meeting."""
    print(f"[join] Navigating to Jitsi: {url}")
    await page.goto(url, wait_until="networkidle", timeout=config.BROWSER_TIMEOUT_MS)

    # Wait for the pre-join screen or direct entry
    await asyncio.sleep(3)

    # Try to set display name if there's a name input
    try:
        name_input = page.locator('input[placeholder*="name" i], input[id*="name" i]').first
        if await name_input.is_visible(timeout=5000):
            await name_input.fill(config.BOT_NAME)
            print(f"[join] Set display name: {config.BOT_NAME}")
    except Exception:
        pass

    # Click "Join meeting" button
    try:
        join_btn = page.locator(
            'button:has-text("Join meeting"), '
            'button:has-text("Join"), '
            'button[data-testid="prejoin.joinMeeting"], '
            'div.prejoin-preview-dropdown-btn'
        ).first
        if await join_btn.is_visible(timeout=5000):
            await join_btn.click()
            print("[join] Clicked Join button")
    except Exception as e:
        print(f"[join] No join button found (may have auto-joined): {e}")

    await asyncio.sleep(3)

    # Mute camera (we don't need video)
    try:
        video_btn = page.locator(
            'div[aria-label*="camera" i], '
            'div[aria-label*="video" i], '
            'button[aria-label*="camera" i]'
        ).first
        if await video_btn.is_visible(timeout=3000):
            await video_btn.click()
            print("[join] Toggled camera off")
    except Exception:
        pass

    print("[join] Successfully joined Jitsi meeting!")


async def join_google_meet(page, url: str):
    """Join a Google Meet meeting.
    
    NOTE: Google Meet typically requires authentication.
    For best results, use a persistent browser profile with a logged-in Google account.
    """
    print(f"[join] Navigating to Google Meet: {url}")
    await page.goto(url, wait_until="networkidle", timeout=config.BROWSER_TIMEOUT_MS)
    await asyncio.sleep(5)

    # Dismiss "Got it" / cookie consent dialogs
    for selector in [
        'button:has-text("Got it")',
        'button:has-text("Accept all")',
        'button:has-text("Dismiss")',
    ]:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                await asyncio.sleep(1)
        except Exception:
            pass

    # Turn off camera and mic before joining (pre-join toggles)
    for label in ["camera", "microphone"]:
        try:
            toggle = page.locator(f'div[aria-label*="Turn off {label}" i], button[aria-label*="Turn off {label}" i]').first
            if await toggle.is_visible(timeout=3000):
                await toggle.click()
                print(f"[join] Turned off {label}")
        except Exception:
            pass

    # Try to enter name for guest access
    try:
        name_input = page.locator('input[placeholder*="name" i], input[aria-label*="name" i]').first
        if await name_input.is_visible(timeout=3000):
            await name_input.fill(config.BOT_NAME)
    except Exception:
        pass

    # Click "Ask to join" or "Join now"
    for text in ["Ask to join", "Join now", "Join"]:
        try:
            btn = page.locator(f'button:has-text("{text}")').first
            if await btn.is_visible(timeout=5000):
                await btn.click()
                print(f"[join] Clicked '{text}'")
                break
        except Exception:
            continue

    await asyncio.sleep(5)
    print("[join] Google Meet join flow complete (may be waiting for host approval)")


async def launch_browser_and_join(url: str, keep_open: bool = True):
    """Launch Chromium with virtual audio and join meeting."""
    platform = detect_platform(url)
    print(f"[join] Detected platform: {platform}")

    async with async_playwright() as p:
        # Chromium launch args for virtual audio
        browser = await p.chromium.launch(
            headless=config.HEADLESS,
            args=[
                "--use-fake-device-for-media-stream",
                "--use-fake-ui-for-media-stream",
                "--autoplay-policy=no-user-gesture-required",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-dev-shm-usage",
                "--no-first-run",
                "--disable-features=WebRtcHideLocalIpsWithMdns",
                # Route audio through our virtual devices
                f"--alsa-output-device=pulse",
            ],
            env={
                **os.environ,
                # Tell PulseAudio which sink/source to use
                "PULSE_SINK": config.SINK_NAME,
                "PULSE_SOURCE": "vmic-source",
            },
        )

        context = await browser.new_context(
            permissions=["microphone", "camera", "notifications"],
            user_agent=config.USER_AGENT,
            viewport={"width": 1280, "height": 720},
        )

        page = await context.new_page()

        # Join based on platform
        if platform == "jitsi":
            await join_jitsi(page, url)
        elif platform == "google-meet":
            await join_google_meet(page, url)
        else:
            print(f"[join] Unknown platform, just navigating to URL...")
            await page.goto(url, wait_until="networkidle", timeout=config.BROWSER_TIMEOUT_MS)

        if keep_open:
            print("[join] Browser is running. Press Ctrl+C to exit.")
            try:
                while True:
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                print("[join] Shutting down...")

        await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python join_meeting.py <meeting-url>")
        print("Example: python join_meeting.py https://meet.jit.si/my-test-room")
        sys.exit(1)

    url = sys.argv[1]
    asyncio.run(launch_browser_and_join(url))
