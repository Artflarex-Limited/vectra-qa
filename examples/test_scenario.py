#!/usr/bin/env python3
"""
Multi-Agent Test Scenario: User Authentication Flow
Demonstrates the complete agent lifecycle:
1. Orchestrator spawns UI Explorer
2. UI Explorer logs in and writes to UI_State_Log
3. Orchestrator spawns Data Validator
4. Data Validator confirms session and writes to Data_Validation_Log
5. Orchestrator reads both nodes and updates Test_Run_Master
"""

import sys
import time
import asyncio
from pathlib import Path

# Add parent directory to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcp_server.tools import execute_tool, vault


def log_step(step: str):
    """Print a formatted step log."""
    print(f"\n{'='*60}")
    print(f"STEP: {step}")
    print(f"{'='*60}")


def print_node_state(node_path: str, label: str):
    """Print the current state of a memory node."""
    print(f"\n📄 {label}: {node_path}")
    try:
        node = vault.read_node(node_path)
        fm = node["frontmatter"]
        print(f"   Status: {fm.get('status', 'unknown')}")
        print(f"   Result: {fm.get('result', 'pending')}")
        if fm.get("agent_id"):
            print(f"   Agent ID: {fm['agent_id']}")
        if fm.get("selectors_tested"):
            print(f"   Selectors Tested: {len(fm['selectors_tested'])}")
        if fm.get("requests_intercepted") is not None:
            print(f"   Requests Intercepted: {fm['requests_intercepted']}")
    except Exception as e:
        print(f"   Error: {e}")


async def run_test_scenario():
    """Execute the multi-agent test scenario."""

    print("\n🚀 VECTRA QA - Multi-Agent Test Scenario")
    print("=" * 60)
    print("Test: User Authentication Flow")
    print("=" * 60)

    # Step 1: Initialize Orchestrator
    log_step("1. Orchestrator initializes test run")

    vault.update_frontmatter(
        "Global/Test_Run_Master.md",
        {"status": "running", "phase": "execution", "modified": "2025-05-24T14:45:00Z"},
    )

    print("✅ Test_Run_Master updated: status=running, phase=execution")
    print_node_state("Global/Test_Run_Master.md", "Orchestrator State")

    # Step 2: Spawn UI Explorer
    log_step("2. Orchestrator spawns UI Explorer agent")

    spawn_result = execute_tool(
        "spawn_agent",
        {
            "role": "ui_explorer",
            "objective": "Verify login form rendering, test input validation, and simulate user login workflow",
            "memory_node": "Runs/Login_Flow_UI.md",
        },
    )

    if spawn_result["status"] == "success":
        ui_agent = spawn_result["result"]
        print(f"✅ UI Explorer spawned:")
        print(f"   Agent ID: {ui_agent['agent_id']}")
        print(f"   PID: {ui_agent['pid']}")
        print(f"   Memory Node: {ui_agent['memory_node']}")

        # Update Test_Run_Master
        vault.update_frontmatter(
            "Global/Test_Run_Master.md",
            {"active_agents": [ui_agent["agent_id"]], "phase": "execution"},
        )
    else:
        print(f"❌ Failed to spawn UI Explorer: {spawn_result.get('error')}")
        return

    # Step 3: UI Explorer executes tests
    log_step("3. UI Explorer executes frontend tests")

    # Simulate UI testing activities
    vault.update_frontmatter(
        "Runs/Login_Flow_UI.md",
        {
            "status": "active",
            "last_action": "query_selector",
            "selectors_tested": ["#login-form", "#username", "#password", "#login-btn"],
            "interactions_logged": 3,
        },
    )

    # Simulate writing findings
    vault.write_node(
        "Runs/Login_Flow_UI.md",
        content="""# UI Explorer Agent Log

## Objective
Verify login form rendering, test input validation, and simulate user login workflow

## Progress
- **Started**: 2025-05-24T14:45:00Z
- **Last Action**: simulated_interaction
- **Status**: active

## DOM Snapshots

### Login Form Initial State
- Form container: `#login-form` (visible, display: block)
- Username field: `#username` (visible, placeholder="Enter username")
- Password field: `#password` (visible, type="password")
- Submit button: `#login-btn` (visible, text="Sign In", enabled)

## CSS Selectors Tested
1. ✅ `#login-form` - Found, visible, dimensions 400x300px
2. ✅ `#username` - Found, visible, accepts text input
3. ✅ `#password` - Found, visible, masks input correctly
4. ✅ `#login-btn` - Found, visible, hover state changes background to #2563eb

## Interactions Log
1. **click** on `#username` → Focus ring visible, cursor positioned
2. **type** "test_user" into `#username` → Value updated, validation passed
3. **type** "***" into `#password` → Value masked, no plain text leak
4. **click** on `#login-btn` → Button shows loading state, form submitted

## Anomalies & Issues
- [INFO] Password field lacks `aria-describedby` for password requirements
- [WARNING] Login button doesn't disable during form submission (race condition risk)

## Confidence Score: 87%

## Wiki-Links
- [[Test_Run_Master]] - Parent test run
- [[Data_Validation_Log]] - Backend validation context""",
        frontmatter={
            "agent_role": "ui_explorer",
            "agent_id": ui_agent["agent_id"],
            "status": "completed",
            "last_action": "write_findings",
            "objective": "Verify login form rendering, test input validation, and simulate user login workflow",
            "start_time": "2025-05-24T14:45:00Z",
            "end_time": "2025-05-24T14:45:30Z",
            "result": "pass",
            "selectors_tested": ["#login-form", "#username", "#password", "#login-btn"],
            "interactions_logged": 4,
            "anomalies_found": 2,
            "confidence_score": 87,
        },
    )

    print("✅ UI Explorer completed tests and wrote findings")
    print_node_state("Runs/Login_Flow_UI.md", "UI Explorer Results")

    # Step 4: Spawn Data Validator
    log_step("4. Orchestrator spawns Data Validator agent")

    spawn_result = execute_tool(
        "spawn_agent",
        {
            "role": "data_validator",
            "objective": "Intercept login API call, validate JWT structure, verify session persistence",
            "memory_node": "Runs/Login_Flow_Validation.md",
        },
    )

    if spawn_result["status"] == "success":
        data_agent = spawn_result["result"]
        print(f"✅ Data Validator spawned:")
        print(f"   Agent ID: {data_agent['agent_id']}")
        print(f"   PID: {data_agent['pid']}")
        print(f"   Memory Node: {data_agent['memory_node']}")

        # Update Test_Run_Master
        current = vault.read_node("Global/Test_Run_Master.md")
        active = current["frontmatter"].get("active_agents", [])
        active.append(data_agent["agent_id"])
        vault.update_frontmatter("Global/Test_Run_Master.md", {"active_agents": active})
    else:
        print(f"❌ Failed to spawn Data Validator: {spawn_result.get('error')}")
        return

    # Step 5: Data Validator executes tests
    log_step("5. Data Validator executes backend validation")

    vault.write_node(
        "Runs/Login_Flow_Validation.md",
        content="""# Data Validator Agent Log

## Objective
Intercept login API call, validate JWT structure, verify session persistence

## Progress
- **Started**: 2025-05-24T14:45:35Z
- **Last Action**: validate_schema
- **Status**: active

## Network Requests

### Request 1: POST /api/auth/login
- **Triggered by**: User click on [[UI_State_Log#login-btn]]
- **Status**: 200 OK
- **Duration**: 145ms
- **Content-Type**: application/json

#### Request Payload
```json
{"username": "test_user", "password": "***"}
```

#### Response Payload
```json
{
  "token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "dGhpcyBpcyBhIHJlZnJlc2ggdG9rZW4...",
  "user": {
    "id": 123,
    "username": "test_user",
    "email": "test@example.com"
  }
}
```

## JWT Analysis
```yaml
algorithm: RS256
header:
  alg: RS256
  typ: JWT
payload:
  sub: "user-123"
  iss: "vectra-auth"
  aud: "vectra-app"
  iat: 1748097935
  exp: 1748101535
  role: "user"
signature: Valid (verified with public key)
```

## Schema Validation Results
- ✅ token: string (JWT format, length > 100)
- ✅ refresh_token: string (length > 50)
- ✅ user.id: integer (positive)
- ✅ user.username: string (matches request)
- ✅ user.email: string (valid email format)
- ⚠️ [INFO] No `expires_in` field (not required by schema but recommended)

## Session Verification
- Session ID: `sess_abc123xyz`
- Cookie: HttpOnly, Secure, SameSite=Strict ✅
- Session stored in Redis: Confirmed ✅
- TTL: 3600 seconds ✅

## Database Mutations
- ✅ User last_login timestamp updated
- ✅ Login audit log entry created
- ✅ Session record inserted into sessions table

## Anomalies & Issues
- None detected

## Wiki-Links
- [[Test_Run_Master]] - Parent test run
- [[UI_State_Log]] - Frontend testing context
- [[Runs/Login_Flow_UI.md]] - UI Explorer findings""",
        frontmatter={
            "agent_role": "data_validator",
            "agent_id": data_agent["agent_id"],
            "status": "completed",
            "last_action": "write_findings",
            "objective": "Intercept login API call, validate JWT structure, verify session persistence",
            "start_time": "2025-05-24T14:45:35Z",
            "end_time": "2025-05-24T14:46:05Z",
            "result": "pass",
            "requests_intercepted": 1,
            "payloads_validated": 2,
            "schema_mismatches": 0,
            "jwt_tokens_decoded": 1,
        },
    )

    print("✅ Data Validator completed tests and wrote findings")
    print_node_state("Runs/Login_Flow_Validation.md", "Data Validator Results")

    # Step 6: Orchestrator compiles final report
    log_step("6. Orchestrator compiles final E2E test report")

    # Move agents to completed
    vault.update_frontmatter(
        "Global/Test_Run_Master.md",
        {
            "active_agents": [],
            "completed_agents": [ui_agent["agent_id"], data_agent["agent_id"]],
            "pass_count": 2,
            "fail_count": 0,
            "skip_count": 0,
            "status": "completed",
            "phase": "reporting",
            "overall_result": "pass",
            "modified": "2025-05-24T14:46:10Z",
        },
    )

    # Append final report to Test_Run_Master
    current_node = vault.read_node("Global/Test_Run_Master.md")
    report_content = (
        current_node["content"]
        + "\n\n## Final Report\n\n"
        + "### Test Run Summary\n"
        + "- **Status**: ✅ PASSED\n"
        + "- **Duration**: 70 seconds\n"
        + "- **Agents Spawned**: 2\n"
        + "- **Agents Completed**: 2\n\n"
        + "### Detailed Results\n"
        + f"- **UI Explorer** ({ui_agent['agent_id']}): ✅ PASSED\n"
        + "  - Selectors Tested: 4\n"
        + "  - Interactions: 4\n"
        + "  - Confidence: 87%\n"
        + "  - Issues: 2 minor (accessibility, race condition risk)\n"
        + "  - Memory Node: [[Runs/Login_Flow_UI.md]]\n\n"
        + f"- **Data Validator** ({data_agent['agent_id']}): ✅ PASSED\n"
        + "  - Requests Intercepted: 1\n"
        + "  - Payloads Validated: 2\n"
        + "  - Schema Mismatches: 0\n"
        + "  - JWT Valid: Yes (RS256, expires in 1 hour)\n"
        + "  - Memory Node: [[Runs/Login_Flow_Validation.md]]\n\n"
        + "### Findings\n"
        + "1. Login form renders correctly with all expected elements\n"
        + "2. Input validation works as expected\n"
        + "3. API responds correctly with valid JWT token\n"
        + "4. Session persistence verified (Redis + Secure Cookie)\n"
        + "5. Minor accessibility improvement recommended for password field\n\n"
        + "### Recommendations\n"
        + "- Add `aria-describedby` to password field for screen readers\n"
        + "- Disable login button during form submission to prevent race conditions\n"
        + "- Consider adding `expires_in` to login response for better client handling\n\n"
        + "## Orchestrator Notes\n"
        + "- Test run completed successfully at 2025-05-24T14:46:10Z\n"
        + "- Both agents terminated gracefully, compute resources freed\n"
        + "- Overall system health: GOOD"
    )

    vault.write_node("Global/Test_Run_Master.md", report_content, current_node["frontmatter"])

    print("✅ Test_Run_Master updated with final report")
    print_node_state("Global/Test_Run_Master.md", "Final State")

    # Step 7: Terminate agents
    log_step("7. Gracefully terminate all agents")

    execute_tool("terminate_agent", {"agent_id": ui_agent["agent_id"]})
    print(f"✅ UI Explorer ({ui_agent['agent_id']}) terminated")

    execute_tool("terminate_agent", {"agent_id": data_agent["agent_id"]})
    print(f"✅ Data Validator ({data_agent['agent_id']}) terminated")

    print("\n" + "=" * 60)
    print("🏁 TEST SCENARIO COMPLETED SUCCESSFULLY")
    print("=" * 60)
    print("\nTo view live dashboard:")
    print("  1. Start the Command Center: python command_center/main.py")
    print("  2. Open browser to: http://localhost:3000")
    print("\nTo view Obsidian vault:")
    print(f"  Open folder: {vault.vault_path}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(run_test_scenario())
