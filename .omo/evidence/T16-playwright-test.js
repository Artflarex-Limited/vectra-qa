const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

(async () => {
    const browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
    const page = await context.newPage();

    const evidenceDir = '/home/bugra/Documents/projects/vectra-qa/.omo/evidence';

    // ── Scenario 1: Greeting renders ──
    console.log('=== Scenario 1: Chat panel renders greeting ===');
    
    await page.goto('http://localhost:3000/');
    await page.waitForLoadState('networkidle');

    // Click the chat panel header to expand
    await page.click('#chat-panel-container .chat-panel-header');
    await page.waitForTimeout(300);

    // Click Start button
    await page.click('text=Start');
    
    // Wait for greeting bubble
    await page.waitForSelector('.chat-bubble assistant:has-text("Vectra")', { timeout: 5000 });
    
    // Take screenshot
    await page.screenshot({ path: path.join(evidenceDir, 'T16-greeting.png') });
    console.log('✓ Scenario 1 PASS — greeting visible');

    // ── Scenario 2: AskQuestionEvent renders input ──
    console.log('=== Scenario 2: AskQuestionEvent renders input ===');

    // Mock the message endpoint to return an AskQuestionEvent
    await page.route('**/api/engineer/*/message', async (route) => {
        const postData = route.request().postData();
        const body = JSON.parse(postData || '{}');
        
        if (body.message === 'https://example.com') {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    events: [{
                        type: 'classify_site',
                        session_id: 'test-session',
                        stage: 'recon',
                        timestamp: new Date().toISOString(),
                        site_type: 'ECOMMERCE',
                        confidence: 0.85,
                        signals: ['cart_count', 'product-grid']
                    }, {
                        type: 'confirm_classification',
                        session_id: 'test-session',
                        stage: 'recon',
                        timestamp: new Date().toISOString()
                    }]
                }),
                stage: 'recon'
            });
        } else if (body.message === 'yes') {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    events: [{
                        type: 'ask_question',
                        session_id: 'test-session',
                        stage: 'context',
                        timestamp: new Date().toISOString(),
                        question_id: 'q1',
                        prompt: 'Do you need to log in to test the checkout flow?',
                        choices: null
                    }]
                }),
                stage: 'context'
            });
        } else {
            await route.continue();
        }
    });

    // Type URL and submit
    await page.fill('#chat-input', 'https://example.com');
    await page.keyboard.press('Enter');
    await page.waitForTimeout(500);

    // Wait for classify badge
    await page.waitForSelector('text=Classified as: ECOMMERCE', { timeout: 3000 });
    
    // Click Yes to confirm
    await page.click('text=Yes, that\'s right');
    await page.waitForTimeout(500);

    // Wait for question and assert input visible
    await page.waitForSelector('text=Do you need to log in', { timeout: 3000 });
    const inputVisible = await page.isVisible('#chat-input');
    
    if (!inputVisible) {
        throw new Error('Text input not visible after AskQuestionEvent');
    }
    
    await page.screenshot({ path: path.join(evidenceDir, 'T16-question.png') });
    console.log('✓ Scenario 2 PASS — text input visible after question');

    // ── Scenario 3: NarrateEvent streams in ──
    console.log('=== Scenario 3: NarrateEvent streams in ===');

    // Mock the message endpoint for "run all"
    await page.route('**/api/engineer/*/message', async (route) => {
        const postData = route.request().postData();
        const body = JSON.parse(postData || '{}');
        
        if (body.message === 'run all') {
            await route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    events: [{
                        type: 'plan_proposed',
                        session_id: 'test-session',
                        stage: 'plan',
                        timestamp: new Date().toISOString(),
                        tests: ['homepage', 'cart_flow', 'checkout_flow'],
                        site_type: 'ECOMMERCE'
                    }]
                }),
                stage: 'plan'
            });
        } else {
            await route.continue();
        }
    });

    // Mock the SSE stream to inject a narrate event
    await page.route('**/api/engineer/*/stream', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'text/event-stream',
            body: `data: {"type":"test_started","session_id":"test-session","stage":"execute","timestamp":"${new Date().toISOString()}","test_id":"homepage","role":"ui_explorer"}\n\ndata: {"type":"narrate","session_id":"test-session","stage":"execute","timestamp":"${new Date().toISOString()}","agent_id":"agent-123","status":"running","message":"Opening the homepage and checking the hero section."}\n\n`,
            headers: {
                'Cache-Control': 'no-cache',
                'Connection': 'keep-alive'
            }
        });
    });

    // Now we need to get to the plan view first. Let's mock the start to give us a plan.
    await page.evaluate(() => {
        // Inject a plan proposed event directly
        renderEngineerEvent({
            type: 'plan_proposed',
            session_id: 'test-session',
            stage: 'plan',
            timestamp: new Date().toISOString(),
            tests: ['homepage', 'cart_flow', 'checkout_flow'],
            site_type: 'ECOMMERCE'
        });
    });
    await page.waitForTimeout(300);

    // Click Run
    await page.click('text=Run');
    await page.waitForTimeout(2000);

    // Assert narration bubble appeared
    const narrateVisible = await page.isVisible('text=Opening the homepage');
    if (!narrateVisible) {
        throw new Error('Narration bubble not visible');
    }

    await page.screenshot({ path: path.join(evidenceDir, 'T16-narration.png') });
    console.log('✓ Scenario 3 PASS — narration bubble visible');

    // ── AC#3: Resume on refresh ──
    console.log('=== AC#3: Resume on refresh ===');
    
    // Set a session cookie
    await context.addCookies([{
        name: 'session_id',
        value: 'test-resume-session',
        domain: 'localhost',
        path: '/'
    }]);

    // Mock resume endpoint
    await page.route('**/api/engineer/test-resume-session/resume', async (route) => {
        await route.fulfill({
            status: 200,
            contentType: 'application/json',
            body: JSON.stringify({
                events: [{
                    type: 'greeting',
                    session_id: 'test-resume-session',
                    stage: 'greeting',
                    timestamp: new Date().toISOString(),
                    message: 'Welcome back! I\'m Vectra.'
                }],
                stage: 'greeting'
            })
        });
    });

    // Refresh page
    await page.reload();
    await page.waitForLoadState('networkidle');
    await page.click('#chat-panel-container .chat-panel-header');
    await page.waitForTimeout(300);

    // Assert greeting is restored
    const resumeGreeting = await page.isVisible('text=Welcome back!');
    if (!resumeGreeting) {
        throw new Error('Resume failed — greeting not restored');
    }
    console.log('✓ AC#3 PASS — conversation resumes after refresh');

    await browser.close();
    console.log('\n=== ALL SCENARIOS PASSED ===');
})();
