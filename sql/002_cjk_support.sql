-- Migration: Add CJK (jieba) tokenization support to PostgreSQL backend.
-- Safe to run multiple times (uses IF NOT EXISTS / ADD COLUMN IF NOT EXISTS).

-- 1. Add jieba-tokenized text column to pages
ALTER TABLE pages ADD COLUMN IF NOT EXISTS text_jieba TEXT;

CREATE INDEX IF NOT EXISTS idx_pages_jieba ON pages USING GIN(
    to_tsvector('simple', COALESCE(text_jieba, ''))
);

-- 2. Add pinned + jieba columns to memories
ALTER TABLE memories ADD COLUMN IF NOT EXISTS pinned BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE memories ADD COLUMN IF NOT EXISTS content_jieba TEXT;

CREATE INDEX IF NOT EXISTS idx_memories_jieba ON memories USING GIN(
    to_tsvector('simple', COALESCE(content_jieba, ''))
);
