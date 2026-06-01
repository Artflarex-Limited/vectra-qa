-- Vectra QA Database Schema
-- PostgreSQL + pgvector
-- Run automatically by docker-compose on first startup

-- Enable pgvector extension for embeddings
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- CORE TABLES
-- ============================================

CREATE TABLE IF NOT EXISTS test_runs (
    id TEXT PRIMARY KEY,
    objective TEXT NOT NULL,
    target_url TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TIMESTAMPTZ DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_test_runs_status ON test_runs(status);
CREATE INDEX IF NOT EXISTS idx_test_runs_started_at ON test_runs(started_at);

CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL,
    pid INTEGER,
    status TEXT NOT NULL DEFAULT 'active',
    memory_node_path TEXT,
    test_run_id TEXT REFERENCES test_runs(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_agents_test_run ON agents(test_run_id);
CREATE INDEX IF NOT EXISTS idx_agents_status ON agents(status);

CREATE TABLE IF NOT EXISTS findings (
    id SERIAL PRIMARY KEY,
    test_run_id TEXT REFERENCES test_runs(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    description TEXT,
    severity TEXT NOT NULL DEFAULT 'info',
    category TEXT,
    source_url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_findings_test_run ON findings(test_run_id);
CREATE INDEX IF NOT EXISTS idx_findings_agent ON findings(agent_id);
CREATE INDEX IF NOT EXISTS idx_findings_severity ON findings(severity);

CREATE TABLE IF NOT EXISTS metrics (
    id SERIAL PRIMARY KEY,
    test_run_id TEXT REFERENCES test_runs(id) ON DELETE CASCADE,
    agent_id TEXT REFERENCES agents(id) ON DELETE SET NULL,
    metric_name TEXT NOT NULL,
    metric_value DECIMAL(12,4),
    unit TEXT,
    metadata JSONB DEFAULT '{}',
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_metrics_test_run ON metrics(test_run_id);
CREATE INDEX IF NOT EXISTS idx_metrics_name ON metrics(metric_name);

-- ============================================
-- LLM CACHE (Replaces JSON file cache)
-- ============================================

CREATE TABLE IF NOT EXISTS llm_cache (
    hash_key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    content TEXT NOT NULL,
    provider TEXT,
    usage_tokens INTEGER,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_llm_cache_expires ON llm_cache(expires_at);

-- Cleanup expired cache entries (run periodically or via cron)
CREATE OR REPLACE FUNCTION cleanup_expired_cache()
RETURNS INTEGER AS $$
DECLARE
    deleted_count INTEGER;
BEGIN
    DELETE FROM llm_cache WHERE expires_at < NOW();
    GET DIAGNOSTICS deleted_count = ROW_COUNT;
    RETURN deleted_count;
END;
$$ LANGUAGE plpgsql;

-- ============================================
-- LLM USAGE TRACKING (Cost control)
-- ============================================

CREATE TABLE IF NOT EXISTS llm_usage (
    id SERIAL PRIMARY KEY,
    model TEXT NOT NULL,
    provider TEXT NOT NULL,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost_usd DECIMAL(10,6) DEFAULT 0.000000,
    test_run_id TEXT REFERENCES test_runs(id) ON DELETE SET NULL,
    cache_hit BOOLEAN DEFAULT FALSE,
    timestamp TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_test_run ON llm_usage(test_run_id);
CREATE INDEX IF NOT EXISTS idx_llm_usage_timestamp ON llm_usage(timestamp);
CREATE INDEX IF NOT EXISTS idx_llm_usage_model ON llm_usage(model);

-- View for cost aggregation
CREATE OR REPLACE VIEW llm_cost_summary AS
SELECT
    test_run_id,
    model,
    provider,
    SUM(input_tokens) AS total_input_tokens,
    SUM(output_tokens) AS total_output_tokens,
    SUM(cost_usd) AS total_cost_usd,
    COUNT(*) FILTER (WHERE cache_hit) AS cache_hits,
    COUNT(*) FILTER (WHERE NOT cache_hit) AS cache_misses,
    MIN(timestamp) AS first_call,
    MAX(timestamp) AS last_call
FROM llm_usage
GROUP BY test_run_id, model, provider;

-- ============================================
-- RAG DOCUMENTS (Vector search)
-- ============================================

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    source_path TEXT NOT NULL,
    content TEXT NOT NULL,
    doc_type TEXT NOT NULL DEFAULT 'unknown',
    title TEXT,
    metadata JSONB DEFAULT '{}',
    embedding vector(1536),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_path);
CREATE INDEX IF NOT EXISTS idx_documents_type ON documents(doc_type);

-- Full-text search index for hybrid search
CREATE INDEX IF NOT EXISTS idx_documents_fts ON documents 
    USING gin(to_tsvector('english', content || ' ' || COALESCE(title, '')));

CREATE TABLE IF NOT EXISTS document_chunks (
    id SERIAL PRIMARY KEY,
    document_id INTEGER REFERENCES documents(id) ON DELETE CASCADE,
    chunk_text TEXT NOT NULL,
    chunk_index INTEGER NOT NULL,
    embedding vector(1536),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON document_chunks(document_id);

-- HNSW index for fast approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS idx_chunks_embedding 
    ON document_chunks USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ============================================
-- OBSIDIAN VAULT SYNC LOG
-- Tracks which nodes have been synced to PostgreSQL
-- ============================================

CREATE TABLE IF NOT EXISTS vault_sync_log (
    node_path TEXT PRIMARY KEY,
    last_modified TIMESTAMPTZ,
    synced_at TIMESTAMPTZ DEFAULT NOW(),
    checksum TEXT,
    action TEXT DEFAULT 'synced'
);

CREATE INDEX IF NOT EXISTS idx_vault_sync_log_time ON vault_sync_log(synced_at);

-- ============================================
-- E-COMMERCE TEST CONFIGURATIONS
-- ============================================

CREATE TABLE IF NOT EXISTS ecommerce_platforms (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    selector_map JSONB NOT NULL DEFAULT '{}',
    base_url TEXT,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ecommerce_test_results (
    id SERIAL PRIMARY KEY,
    test_run_id TEXT REFERENCES test_runs(id) ON DELETE CASCADE,
    platform_id TEXT REFERENCES ecommerce_platforms(id),
    test_type TEXT NOT NULL,
    test_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    findings JSONB DEFAULT '[]',
    metrics JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_ecommerce_results_test_run ON ecommerce_test_results(test_run_id);

-- Insert default platforms
INSERT INTO ecommerce_platforms (id, name, selector_map) VALUES
('optozon', 'Optozon', '{}'),
('shopify', 'Shopify', '{}'),
('woocommerce', 'WooCommerce', '{}'),
('magento', 'Magento', '{}'),
('custom', 'Custom Platform', '{}')
ON CONFLICT (id) DO NOTHING;

-- ============================================
-- HELPER FUNCTIONS
-- ============================================

-- Search document chunks by vector similarity
CREATE OR REPLACE FUNCTION search_similar_chunks(
    query_embedding vector(1536),
    match_count INTEGER DEFAULT 5,
    similarity_threshold DECIMAL DEFAULT 0.7
)
RETURNS TABLE(
    chunk_id INTEGER,
    document_id INTEGER,
    chunk_text TEXT,
    similarity DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        dc.id AS chunk_id,
        dc.document_id,
        dc.chunk_text,
        1 - (dc.embedding <=> query_embedding) AS similarity
    FROM document_chunks dc
    WHERE 1 - (dc.embedding <=> query_embedding) > similarity_threshold
    ORDER BY dc.embedding <=> query_embedding
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- Hybrid search: vector similarity + full-text ranking
CREATE OR REPLACE FUNCTION hybrid_search_documents(
    query_text TEXT,
    query_embedding vector(1536),
    match_count INTEGER DEFAULT 5
)
RETURNS TABLE(
    doc_id INTEGER,
    source_path TEXT,
    content TEXT,
    combined_score DECIMAL
) AS $$
BEGIN
    RETURN QUERY
    WITH vector_scores AS (
        SELECT
            d.id,
            1 - (d.embedding <=> query_embedding) AS v_score
        FROM documents d
        WHERE d.embedding IS NOT NULL
    ),
    text_scores AS (
        SELECT
            d.id,
            ts_rank(
                to_tsvector('english', d.content || ' ' || COALESCE(d.title, '')),
                plainto_tsquery('english', query_text)
            ) AS t_score
        FROM documents d
        WHERE to_tsvector('english', d.content || ' ' || COALESCE(d.title, '')) 
              @@ plainto_tsquery('english', query_text)
    )
    SELECT
        d.id AS doc_id,
        d.source_path,
        LEFT(d.content, 500) AS content,
        COALESCE(v.v_score, 0) * 0.7 + COALESCE(t.t_score, 0) * 0.3 AS combined_score
    FROM documents d
    LEFT JOIN vector_scores v ON d.id = v.id
    LEFT JOIN text_scores t ON d.id = t.id
    WHERE v.v_score IS NOT NULL OR t.t_score IS NOT NULL
    ORDER BY combined_score DESC
    LIMIT match_count;
END;
$$ LANGUAGE plpgsql;
