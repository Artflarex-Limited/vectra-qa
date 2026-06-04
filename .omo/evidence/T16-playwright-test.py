import asyncio
from playwright.async_api import async_playwright
import json
from datetime import datetime, timezone

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1280, 'height': 900})
        page = await context.new_page()
        
        evidence_dir = '/home/bugra/Documents/projects/vectra-qa/.omo/evidence'
        
        # ── Scenario 1: Greeting renders ──
        print('=== Scenario 1: Chat panel renders greeting ===')
        
        await page.goto('http://localhost:3000/')
        await page.wait_for_timeout(2000)
        
        # Click the chat panel header to expand
        await page.click('#chat-panel-container .chat-panel-header')
        await page.wait_for_timeout(500)
        
        # Click Start button
        start_btn = await page.query_selector('#chat-start-overlay button')
        if start_btn:
            await start_btn.click()
        else:
            raise Exception('Start button not found')
        
        # Wait for the network request to complete and UI to update
        await page.wait_for_timeout(2000)
        
        # Check that greeting bubble appeared
        bubbles = await page.query_selector_all('.chat-bubble')
        if len(bubbles) == 0:
            # Debug: take screenshot
            await page.screenshot(path=f'{evidence_dir}/T16-debug.png')
            raise Exception('No chat bubbles found after starting session')
        
        await page.screenshot(path=f'{evidence_dir}/T16-greeting.png')
        print(f'✓ Scenario 1 PASS — {len(bubbles)} greeting bubble(s) visible')
        
        # ── Scenario 2: AskQuestionEvent renders input ──
        print('=== Scenario 2: AskQuestionEvent renders input ===')
        
        # Mock the message endpoint
        async def handle_message_route(route):
            post_data = route.request.post_data
            body = json.loads(post_data or '{}')
            
            if body.get('message') == 'https://example.com':
                await route.fulfill(
                    status=200,
                    content_type='application/json',
                    body=json.dumps({
                        'events': [{
                            'type': 'classify_site',
                            'session_id': 'test-session',
                            'stage': 'recon',
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'site_type': 'ECOMMERCE',
                            'confidence': 0.85,
                            'signals': ['cart_count', 'product-grid']
                        }, {
                            'type': 'confirm_classification',
                            'session_id': 'test-session',
                            'stage': 'recon',
                            'timestamp': datetime.now(timezone.utc).isoformat()
                        }],
                        'stage': 'recon'
                    })
                )
            elif body.get('message') == 'yes':
                await route.fulfill(
                    status=200,
                    content_type='application/json',
                    body=json.dumps({
                        'events': [{
                            'type': 'ask_question',
                            'session_id': 'test-session',
                            'stage': 'context',
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'question_id': 'q1',
                            'prompt': 'Do you need to log in to test the checkout flow?',
                            'choices': None
                        }],
                        'stage': 'context'
                    })
                )
            else:
                await route.continue_()
        
        await page.route('**/api/engineer/*/message', handle_message_route)
        
        # Type URL and submit
        chat_input = await page.query_selector('#chat-input')
        if not chat_input:
            raise Exception('Chat input not found')
        await chat_input.fill('https://example.com')
        await chat_input.press('Enter')
        await page.wait_for_timeout(1000)
        
        # Wait for classify badge
        classify_visible = await page.is_visible('text=Classified as: ECOMMERCE')
        if not classify_visible:
            await page.screenshot(path=f'{evidence_dir}/T16-debug2.png')
            raise Exception('Classify badge not visible')
        
        # Click Yes to confirm
        yes_btn = await page.query_selector('text=Confirm')
        if yes_btn:
            await yes_btn.click()
        await page.wait_for_timeout(1000)
        
        # Wait for question and assert input visible
        question_visible = await page.is_visible('text=Do you need to log in')
        if not question_visible:
            await page.screenshot(path=f'{evidence_dir}/T16-debug3.png')
            raise Exception('Question not visible')
        
        input_visible = await page.is_visible('#chat-input')
        if not input_visible:
            raise Exception('Text input not visible after AskQuestionEvent')
        
        await page.screenshot(path=f'{evidence_dir}/T16-question.png')
        print('✓ Scenario 2 PASS — text input visible after question')
        
        # ── Scenario 3: NarrateEvent streams in ──
        print('=== Scenario 3: NarrateEvent streams in ===')
        
        # Inject a plan proposed event directly
        await page.evaluate('''() => {
            renderEngineerEvent({
                type: 'plan_proposed',
                session_id: 'test-session',
                stage: 'plan',
                timestamp: new Date().toISOString(),
                tests: ['homepage', 'cart_flow', 'checkout_flow'],
                site_type: 'ECOMMERCE'
            });
        }''')
        await page.wait_for_timeout(500)
        
        # Click Run — mock the backend to avoid fallback
        async def handle_run_route(route):
            post_data = route.request.post_data
            body = json.loads(post_data or '{}')
            if body.get('message') == 'run all':
                await route.fulfill(
                    status=200,
                    content_type='application/json',
                    body=json.dumps({
                        'events': [{
                            'type': 'test_started',
                            'session_id': 'test-session',
                            'stage': 'execute',
                            'timestamp': datetime.now(timezone.utc).isoformat(),
                            'test_id': 'homepage',
                            'role': 'ui_explorer'
                        }],
                        'stage': 'execute'
                    })
                )
            else:
                await route.continue_()
        await page.route('**/api/engineer/*/message', handle_run_route)
        
        run_btn = await page.query_selector('text=Run')
        if run_btn:
            await run_btn.click()
        await page.wait_for_timeout(1000)
        
        # Inject narrate event directly (simulating SSE)
        await page.evaluate('''() => {
            renderEngineerEvent({
                type: 'narrate',
                session_id: 'test-session',
                stage: 'execute',
                timestamp: new Date().toISOString(),
                agent_id: 'agent-123',
                status: 'running',
                message: 'Opening the homepage and checking the hero section.'
            });
        }''')
        await page.wait_for_timeout(500)
        
        # Assert narration bubble appeared
        narrate_visible = await page.is_visible('text=Opening the homepage')
        if not narrate_visible:
            await page.screenshot(path=f'{evidence_dir}/T16-debug4.png')
            raise Exception('Narration bubble not visible')
        
        await page.screenshot(path=f'{evidence_dir}/T16-narration.png')
        print('✓ Scenario 3 PASS — narration bubble visible')
        
        # ── AC#3: Resume on refresh ──
        print('=== AC#3: Resume on refresh ===')
        
        # Create a real session via API first
        import urllib.request
        req = urllib.request.Request(
            'http://localhost:3000/api/engineer/start',
            data=b'{}',
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req) as resp:
            start_data = json.loads(resp.read().decode())
        real_sid = start_data['session_id']
        
        # Set the session cookie
        await context.add_cookies([{
            'name': 'session_id',
            'value': real_sid,
            'domain': 'localhost',
            'path': '/'
        }])
        
        # Refresh page
        await page.reload()
        await page.wait_for_timeout(2000)
        
        # Expand panel if collapsed (resume auto-expands, but be safe)
        panel = await page.query_selector('#chat-panel-container')
        if panel:
            is_collapsed = await panel.evaluate('el => el.classList.contains("collapsed")')
            if is_collapsed:
                await page.click('#chat-panel-container .chat-panel-header')
                await page.wait_for_timeout(300)
        
        # Assert greeting is restored (original greeting message)
        await page.wait_for_timeout(1000)
        resume_greeting = await page.is_visible('text=live QA engineer')
        if not resume_greeting:
            await page.screenshot(path=f'{evidence_dir}/T16-debug5.png')
            # Check what's in the chat messages
            msgs = await page.query_selector('#chat-messages')
            if msgs:
                html = await msgs.inner_html()
                print(f'Messages HTML on resume fail: {html[:300]}')
                style = await msgs.get_attribute('style')
                print(f'Messages style: {style}')
            overlay = await page.query_selector('#chat-start-overlay')
            if overlay:
                style = await overlay.get_attribute('style')
                print(f'Overlay style: {style}')
            raise Exception('Resume failed — greeting not restored')
        print('✓ AC#3 PASS — conversation resumes after refresh')
        
        await browser.close()
        print('\n=== ALL SCENARIOS PASSED ===')

if __name__ == '__main__':
    asyncio.run(main())
