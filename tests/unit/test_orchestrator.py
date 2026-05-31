"""
Unit tests for Orchestrator.
Uses mocked LLM router to avoid real API calls.
"""

import pytest
import asyncio
import json
from unittest.mock import Mock, patch, AsyncMock
from datetime import datetime

from agents.orchestrator.orchestrator import Orchestrator, execute_test_plan


class TestOrchestratorBasic:
    """Test Orchestrator initialization and basic operations."""
    
    @pytest.fixture
    def orchestrator(self, vault):
        """Create an Orchestrator instance."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.vault = vault
        orch.spawner = Mock()
        orch.soul = "Test Soul"
        orch.agents_context = "Test Agents"
        return orch
    
    def test_load_persona(self, orchestrator):
        """Should load persona files."""
        # The fixture already set soul/agents_context
        assert orchestrator.soul == "Test Soul"
        assert orchestrator.agents_context == "Test Agents"
    
    def test_build_system_prompt(self, orchestrator):
        """Should build system prompt from context."""
        prompt = orchestrator._build_system_prompt()
        assert "Test Soul" in prompt
        assert "Test Agents" in prompt
        assert "Orchestrator" in prompt


class TestOrchestratorPlanning:
    """Test test plan generation."""
    
    @pytest.fixture
    def orchestrator(self, vault):
        """Create an Orchestrator instance."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.vault = vault
        orch.spawner = Mock()
        orch.soul = "Test Soul"
        orch.agents_context = "Test Agents"
        return orch
    
    @pytest.mark.asyncio
    async def test_plan_tests_success(self, orchestrator):
        """Should generate test plan from objective."""
        mock_response = Mock()
        mock_response.content = json.dumps({
            "test_plan_id": "plan-123",
            "summary": "Test the login flow",
            "tasks": [
                {
                    "task_id": "task-1",
                    "role": "ui_explorer",
                    "objective": "Test login form rendering",
                    "memory_node": "Runs/Login_UI.md",
                    "depends_on": None,
                    "estimated_duration_seconds": 60,
                    "success_criteria": "Form renders correctly"
                }
            ],
            "parallel_groups": [["task-1"]],
            "overall_success_criteria": "Login flow works"
        })
        
        with patch('agents.orchestrator.orchestrator.llm_router') as mock_router:
            mock_router.complete.return_value = mock_response
            
            plan = await orchestrator.plan_tests(
                objective="Test the login flow",
                url="https://example.com/login"
            )
            
            assert plan["test_plan_id"] == "plan-123"
            assert len(plan["tasks"]) == 1
            assert plan["tasks"][0]["role"] == "ui_explorer"
            mock_router.complete.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_plan_tests_fallback_on_invalid_json(self, orchestrator):
        """Should fallback to simple plan on invalid JSON."""
        mock_response = Mock()
        mock_response.content = "Not valid JSON"
        
        with patch('agents.orchestrator.orchestrator.llm_router') as mock_router:
            mock_router.complete.return_value = mock_response
            
            plan = await orchestrator.plan_tests(
                objective="Test something",
                url="https://example.com"
            )
            
            assert "fallback" in plan["test_plan_id"]
            assert len(plan["tasks"]) == 1
            assert plan["tasks"][0]["role"] == "ui_explorer"
    
    @pytest.mark.asyncio
    async def test_plan_tests_with_markdown_json(self, orchestrator):
        """Should parse JSON from markdown code blocks."""
        mock_response = Mock()
        mock_response.content = """```json
        {
            "test_plan_id": "plan-456",
            "summary": "Test",
            "tasks": [],
            "parallel_groups": [],
            "overall_success_criteria": "Pass"
        }
        ```"""
        
        with patch('agents.orchestrator.orchestrator.llm_router') as mock_router:
            mock_router.complete.return_value = mock_response
            
            plan = await orchestrator.plan_tests(
                objective="Test",
                url="https://example.com"
            )
            
            assert plan["test_plan_id"] == "plan-456"


class TestOrchestratorExecution:
    """Test test plan execution."""
    
    @pytest.fixture
    def orchestrator(self, vault):
        """Create an Orchestrator instance."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.vault = vault
        orch.spawner = Mock()
        orch.soul = "Test Soul"
        orch.agents_context = "Test Agents"
        return orch
    
    @pytest.mark.asyncio
    async def test_execute_test_plan(self, orchestrator):
        """Should execute complete test plan."""
        # Mock plan
        test_plan = {
            "test_plan_id": "plan-789",
            "summary": "Test homepage",
            "tasks": [
                {
                    "task_id": "task-1",
                    "role": "ui_explorer",
                    "objective": "Test homepage",
                    "memory_node": "Runs/Homepage_Test.md",
                    "depends_on": None,
                    "estimated_duration_seconds": 60,
                    "success_criteria": "Page loads"
                }
            ],
            "parallel_groups": [["task-1"]],
            "overall_success_criteria": "Homepage works"
        }
        
        # Mock spawner
        orchestrator.spawner.spawn_agent.return_value = {
            "status": "active",
            "agent_id": "ui-explorer-20250101-123456",
            "pid": 12345
        }
        
        # Pre-create the agent's memory node with completed status
        orchestrator.vault.write_node(
            "Runs/Homepage_Test.md",
            content="# Test Complete",
            frontmatter={
                "status": "completed",
                "result": "pass",
                "agent_id": "ui-explorer-20250101-123456"
            }
        )
        
        with patch.object(orchestrator, 'plan_tests', return_value=test_plan):
            with patch.object(orchestrator, '_wait_for_agents', new_callable=AsyncMock) as mock_wait:
                mock_wait.return_value = None
                
                result = await orchestrator.execute_test_plan(
                    objective="Test homepage",
                    url="https://example.com"
                )
                
                assert result["plan_id"] == "plan-789"
                assert result["status"] == "completed"
                orchestrator.spawner.spawn_agent.assert_called_once()


class TestOrchestratorReporting:
    """Test report compilation."""
    
    @pytest.fixture
    def orchestrator(self, vault):
        """Create an Orchestrator instance."""
        orch = Orchestrator.__new__(Orchestrator)
        orch.vault = vault
        orch.spawner = Mock()
        orch.soul = "Test Soul"
        orch.agents_context = "Test Agents"
        return orch
    
    @pytest.mark.asyncio
    async def test_compile_report_all_pass(self, orchestrator):
        """Should compile report with all tasks passing."""
        plan = {
            "test_plan_id": "plan-1",
            "tasks": [
                {"task_id": "task-1", "role": "ui_explorer"},
                {"task_id": "task-2", "role": "data_validator"}
            ]
        }
        
        completed = {
            "task-1": {"agent_id": "agent-1", "result": "pass"},
            "task-2": {"agent_id": "agent-2", "result": "pass"}
        }
        failed = {}
        
        # Pre-create Test_Run_Master
        orchestrator.vault.write_node(
            "Global/Test_Run_Master.md",
            content="# Test Run",
            frontmatter={"test_plan_id": "plan-1", "status": "running"}
        )
        
        result = await orchestrator._compile_report("plan-1", plan, completed, failed)
        
        assert result["overall_result"] == "pass"
        assert result["completed_tasks"] == 2
        assert result["failed_tasks"] == 0
        
        # Verify Test_Run_Master updated
        node = orchestrator.vault.read_node("Global/Test_Run_Master.md")
        assert node["frontmatter"]["overall_result"] == "pass"
    
    @pytest.mark.asyncio
    async def test_compile_report_some_fail(self, orchestrator):
        """Should compile report with some failures."""
        plan = {
            "test_plan_id": "plan-2",
            "tasks": [
                {"task_id": "task-1", "role": "ui_explorer"},
                {"task_id": "task-2", "role": "data_validator"}
            ]
        }
        
        completed = {"task-1": {"agent_id": "agent-1", "result": "pass"}}
        failed = {"task-2": {"reason": "Timeout"}}
        
        orchestrator.vault.write_node(
            "Global/Test_Run_Master.md",
            content="# Test Run",
            frontmatter={"test_plan_id": "plan-2", "status": "running"}
        )
        
        result = await orchestrator._compile_report("plan-2", plan, completed, failed)
        
        assert result["overall_result"] == "partial"
        assert result["completed_tasks"] == 1
        assert result["failed_tasks"] == 1
