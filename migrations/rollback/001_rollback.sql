-- Vectra QA Rollback: 001_init.sql
-- Safely undoes everything created by the initial migration.
-- All DROP statements use IF EXISTS so partially-applied migrations
-- roll back gracefully. Tables are dropped in reverse creation order
-- to respect foreign key dependencies.

-- ============================================
-- Drop functions (depend on tables)
-- ============================================
DROP FUNCTION IF EXISTS hybrid_search_documents;
DROP FUNCTION IF EXISTS search_similar_chunks;
DROP FUNCTION IF EXISTS cleanup_expired_cache;

-- ============================================
-- Drop views
-- ============================================
DROP VIEW IF EXISTS llm_cost_summary;

-- ============================================
-- Drop tables (reverse creation order to respect FKs)
-- ============================================
DROP TABLE IF EXISTS ecommerce_test_results;
DROP TABLE IF EXISTS ecommerce_platforms;
DROP TABLE IF EXISTS vault_sync_log;
DROP TABLE IF EXISTS document_chunks;
DROP TABLE IF EXISTS documents;
DROP TABLE IF EXISTS llm_usage;
DROP TABLE IF EXISTS llm_cache;
DROP TABLE IF EXISTS metrics;
DROP TABLE IF EXISTS findings;
DROP TABLE IF EXISTS agents;
DROP TABLE IF EXISTS test_runs;

-- ============================================
-- Drop migration tracking table
-- ============================================
DROP TABLE IF EXISTS migration_version;
