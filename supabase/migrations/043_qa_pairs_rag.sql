-- Migration: RAG Q&A pairs from human operator conversations
-- Uses pgvector for semantic similarity search on question embeddings

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Q&A pairs table
CREATE TABLE IF NOT EXISTS qa_pairs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES whatsapp_accounts(id) ON DELETE CASCADE,
  question TEXT NOT NULL,
  answer TEXT NOT NULL,
  category TEXT,
  embedding vector(768),
  source TEXT NOT NULL DEFAULT 'manual',
  source_message_id UUID REFERENCES messages(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_qa_pairs_account ON qa_pairs(account_id);
CREATE INDEX IF NOT EXISTS idx_qa_pairs_source ON qa_pairs(source);

-- HNSW index for fast cosine similarity search
CREATE INDEX IF NOT EXISTS idx_qa_pairs_embedding ON qa_pairs
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION qa_pairs_set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_qa_pairs_updated_at ON qa_pairs;
CREATE TRIGGER trg_qa_pairs_updated_at
BEFORE UPDATE ON qa_pairs
FOR EACH ROW EXECUTE FUNCTION qa_pairs_set_updated_at();

-- 3. Similarity search function
CREATE OR REPLACE FUNCTION match_qa_pairs(
  p_account_id UUID,
  p_query_embedding vector(768),
  p_match_count INT DEFAULT 5,
  p_min_similarity FLOAT DEFAULT 0.35
)
RETURNS TABLE (
  id UUID,
  question TEXT,
  answer TEXT,
  category TEXT,
  similarity FLOAT
)
LANGUAGE sql STABLE
AS $$
  SELECT
    qp.id,
    qp.question,
    qp.answer,
    qp.category,
    1 - (qp.embedding <=> p_query_embedding) AS similarity
  FROM qa_pairs qp
  WHERE qp.account_id = p_account_id
    AND qp.embedding IS NOT NULL
    AND 1 - (qp.embedding <=> p_query_embedding) >= p_min_similarity
  ORDER BY qp.embedding <=> p_query_embedding
  LIMIT p_match_count;
$$;
