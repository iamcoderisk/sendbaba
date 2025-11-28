-- Migration: Add sender fields to campaigns table
-- Run this on your PostgreSQL server

-- Add sender fields
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS from_name VARCHAR(255);
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS from_email VARCHAR(255);
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS reply_to VARCHAR(255);
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS preview_text TEXT;
ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP DEFAULT NOW();

-- Verify
SELECT column_name, data_type 
FROM information_schema.columns 
WHERE table_name = 'campaigns' 
ORDER BY ordinal_position;
