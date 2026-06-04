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
        
        page.click("button:has-text('Start')")
        time.sleep(2)
        
        page.wait_for_selector("text=Greeting", timeout=5000)
        
        page.evaluate("""
            () => {
                window.engineerSessionId = window.engineerSessionId || 'test-session';
                const ev = {
                    type: 'ask_credential',
                    session_id: window.engineerSessionId,
                    stage: 'context',
                    timestamp: new Date().toISOString(),
                    field: 'password',
                    reason: 'I need to log in. What is the password?'
                };
                renderEngineerEvent(ev);
            }
        """)
        time.sleep(1)
        
        password_input = page.locator('input[type="password"]')
        assert password_input.is_visible(), "Password input not visible"
        
        page.screenshot(path="/home/bugra/Documents/projects/vectra-qa/.omo/evidence/T17-masked.png")
        
        password_input.fill("secret123")
        time.sleep(0.5)
        
        page.click("text=Submit")
        time.sleep(1.5)
        
        assert password_input.input_value() == "", "Password input not cleared after submit"
        
        page.screenshot(path="/home/bugra/Documents/projects/vectra-qa/.omo/evidence/T17-cleared.png")
        
        confirmation = page.locator("text=Submitted. I won't show this again.")
        assert confirmation.is_visible(), "Confirmation message not visible"
        
        page_content = page.content()
        assert "secret123" not in page_content, "CREDENTIAL LEAKED IN DOM!"
        
        with open("/home/bugra/Documents/projects/vectra-qa/.omo/evidence/T17-no-leak.txt", "w") as f:
            f.write("PASS: 'secret123' not found in page DOM after credential submit.\n")
            f.write(f"DOM length: {len(page_content)} chars\n")
            f.write("No credential leakage detected.\n")
        
        input_type = password_input.get_attribute("type")
        assert input_type == "password", f"Expected type=password, got type={input_type}"
        
        ls_credential = page.evaluate("""
            () => {
                let found = false;
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    const val = localStorage.getItem(key);
                    if (val && val.includes('secret123')) found = true;
                }
                return found;
            }
        """)
        assert not ls_credential, "Credential found in localStorage!"
        
        page.screenshot(path="/home/bugra/Documents/projects/vectra-qa/.omo/evidence/T17-password.png")
        
        print("ALL T17 QA SCENARIOS PASSED")
        
        browser.close()

finally:
    server.terminate()
    try:
        server.wait(timeout=5)
    except:
        server.kill()
