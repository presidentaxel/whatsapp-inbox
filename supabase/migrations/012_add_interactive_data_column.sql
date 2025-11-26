-- Add interactive_data column to store interactive message details
ALTER TABLE messages ADD COLUMN IF NOT EXISTS interactive_data jsonb;

