CREATE TABLE IF NOT EXISTS platform_documents (
  collection TEXT NOT NULL,
  key TEXT NOT NULL,
  payload JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (collection, key)
);
CREATE INDEX IF NOT EXISTS idx_platform_documents_collection_updated
  ON platform_documents(collection, updated_at DESC);

-- Optional V1.1 pgvector backend. Uncomment/use when the vector extension is installed.
-- CREATE EXTENSION IF NOT EXISTS vector;
-- CREATE TABLE IF NOT EXISTS knowledge_vectors (
--   chunk_id TEXT PRIMARY KEY,
--   payload JSONB NOT NULL,
--   embedding vector(128) NOT NULL,
--   updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
-- );
