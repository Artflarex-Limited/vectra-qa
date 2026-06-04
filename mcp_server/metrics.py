"""
Prometheus metrics for Vectra QA MCP Server.
Exposes /metrics endpoint in Prometheus text format.
"""

from prometheus_client import Counter, Gauge, Histogram, REGISTRY, generate_latest

# Counters
TEST_RUNS = Counter(
    "vectra_qa_test_runs_total",
    "Total test runs",
    ["status", "test_type"]
)

AGENTS_SPAWNED = Counter(
    "vectra_qa_agents_spawned_total",
    "Total agents spawned",
    ["role"]
)

LLM_CALLS = Counter(
    "vectra_qa_llm_calls_total",
    "Total LLM API calls",
    ["provider", "model"]
)

# Gauges
ACTIVE_AGENTS = Gauge(
    "vectra_qa_active_agents",
    "Current active agents",
    ["role", "status"]
)

BROWSER_POOL_SIZE = Gauge(
    "vectra_qa_browser_pool_size",
    "Available browsers in pool"
)

# Histograms
LLM_DURATION = Histogram(
    "vectra_qa_llm_request_duration_seconds",
    "LLM request latency",
    ["provider"],
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0]
)

TEST_DURATION = Histogram(
    "vectra_qa_test_duration_seconds",
    "Test execution duration",
    ["test_type"],
    buckets=[1.0, 5.0, 30.0, 60.0, 300.0, 900.0]
)


def get_metrics() -> bytes:
    """Generate Prometheus metrics output."""
    return generate_latest(REGISTRY)


# Convenience functions for incrementing/gauge updates
def record_test_run(status: str, test_type: str, duration: float = 0.0):
    TEST_RUNS.labels(status=status, test_type=test_type).inc()
    if duration > 0:
        TEST_DURATION.labels(test_type=test_type).observe(duration)


def record_agent_spawn(role: str):
    AGENTS_SPAWNED.labels(role=role).inc()


def record_llm_call(provider: str, model: str, duration: float):
    LLM_CALLS.labels(provider=provider, model=model).inc()
    LLM_DURATION.labels(provider=provider).observe(duration)


def set_active_agents(role: str, status: str, count: int):
    ACTIVE_AGENTS.labels(role=role, status=status).set(count)


def set_browser_pool_size(size: int):
    BROWSER_POOL_SIZE.set(size)