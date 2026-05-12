-- Create additional databases needed by LiteLLM and Langfuse.
-- The default 'blackbeard' database is created by POSTGRES_DB env var.
CREATE DATABASE litellm;
CREATE DATABASE langfuse;
