-- Create additional databases needed by LiteLLM and Langfuse.
-- The default 'blackbeard' database is created by POSTGRES_DB env var.
-- These scripts run as POSTGRES_USER (the superuser), so the created
-- databases are automatically owned by the application user.
CREATE DATABASE litellm;
CREATE DATABASE langfuse;
