import subprocess
import sys
import time
import os

env = os.environ.copy()
env["OBSIDIAN_VAULT_PATH"] = "/tmp/vectra_test_vault"
env["COMMAND_CENTER_PORT"] = "3000"

server = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "command_center.main:app", "--host", "0.0.0.0", "--port", "3000"],
    cwd="/home/bugra/Documents/projects/vectra-qa",
    env=env,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
)

time.sleep(3)

try:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        
        page.goto("http://localhost:3000", wait_until="domcontentloaded")
        time.sleep(2)
        
        page.evaluate("() => { toggleChatPanel(); }")
        time.sleep(1)
        
        page.screenshot(path="/home/bugra/Documents/projects/vectra-qa/.omo/evidence/T17_debug6.png")
        
        panel = page.locator("#chat-panel-container")
        classes = panel.get_attribute("class")
        print(f"Panel classes after toggle: {classes}")
        
        start_btn = page.locator("button:has-text('Start')")
        print(f"Start visible: {start_btn.is_visible()}")
        
        browser.close()

finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except:
        server.kill()
