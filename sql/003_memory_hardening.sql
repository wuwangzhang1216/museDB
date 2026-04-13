-- Migration 003: Memory hardening — provenance, confidence decay, workspace isolation
-- Safe to run multiple times (all statements use IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).

-- Provenance: track where each memory came from
ALTER TABLE memories ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'unknown';

-- Provenance: link to the memory this one superseded
ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_id UUID DEFAULT NULL;

-- Confidence decay: Ebbinghaus-inspired memory lifecycle
ALTER TABLE memories ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_accessed TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_count INTEGER NOT NULL DEFAULT 0;

-- Workspace isolation: scope memories to a workspace
ALTER TABLE memories ADD COLUMN IF NOT EXISTS workspace_id TEXT NOT NULL DEFAULT '_default';

CREATE INDEX IF NOT EXISTS idx_memories_workspace ON memories(workspace_id);
CREATE INDEX IF NOT EXISTS idx_memories_confidence ON memories(confidence) WHERE confidence >= 0.3;
