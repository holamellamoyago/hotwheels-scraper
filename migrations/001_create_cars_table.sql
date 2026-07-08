-- ============================================
-- Migration 001: Create cars table for Hot Wheels
-- Run this in Supabase SQL Editor
-- ============================================

-- Enable UUID extension (already enabled in Supabase by default)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Main cars table
CREATE TABLE IF NOT EXISTS cars (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    toy_num TEXT,                          -- Toy number (e.g. "1/250")
    model_name TEXT NOT NULL,               -- Car model name (e.g. "'55 Chevy Bel Air")
    series TEXT,                            -- Series name (e.g. "HW Art Cars")
    series_num TEXT,                        -- Number within series
    year INTEGER NOT NULL,                  -- Release year
    image_url TEXT,                         -- URL to the car image on wiki
    raw_data JSONB,                         -- Original scraped data for debugging
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Unique constraint: same year + toy_num + model_name = same car
-- This lets us upsert without creating duplicates
ALTER TABLE cars DROP CONSTRAINT IF EXISTS cars_year_toy_model_unique;
ALTER TABLE cars ADD CONSTRAINT cars_year_toy_model_unique 
    UNIQUE (year, toy_num, model_name);

-- Indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_cars_year ON cars(year);
CREATE INDEX IF NOT EXISTS idx_cars_model_name ON cars(model_name);
CREATE INDEX IF NOT EXISTS idx_cars_series ON cars(series);
CREATE INDEX IF NOT EXISTS idx_cars_year_series ON cars(year, series);
CREATE INDEX IF NOT EXISTS idx_cars_created_at ON cars(created_at DESC);

-- Full-text search index for searching by model name
CREATE INDEX IF NOT EXISTS idx_cars_model_name_trgm ON cars USING gin (model_name gin_trgm_ops);
-- Note: requires pg_trgm extension:
-- CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- ============================================
-- Auto-update updated_at on row change
-- ============================================
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_cars_updated_at ON cars;
CREATE TRIGGER trigger_cars_updated_at
    BEFORE UPDATE ON cars
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================
-- Enable Row Level Security (RLS) for public read
-- ============================================
ALTER TABLE cars ENABLE ROW LEVEL SECURITY;

-- Allow anonymous read access (so your Flutter app can query without auth)
DROP POLICY IF EXISTS "Allow anonymous read" ON cars;
CREATE POLICY "Allow anonymous read" ON cars
    FOR SELECT
    USING (true);

-- Only allow inserts/updates from the scraper (using service_role key)
DROP POLICY IF EXISTS "Allow service_role write" ON cars;
CREATE POLICY "Allow service_role write" ON cars
    FOR INSERT
    WITH CHECK (true);

DROP POLICY IF EXISTS "Allow service_role update" ON cars;
CREATE POLICY "Allow service_role update" ON cars
    FOR UPDATE
    USING (true)
    WITH CHECK (true);

-- ============================================
-- Series table (optional, for normalized data)
-- ============================================
CREATE TABLE IF NOT EXISTS series (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL UNIQUE,
    description TEXT,
    first_year INTEGER,
    last_year INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_series_name ON series(name);

-- ============================================
-- View: latest cars per model (for "newest additions")
-- ============================================
CREATE OR REPLACE VIEW latest_cars AS
SELECT DISTINCT ON (model_name) *
FROM cars
ORDER BY model_name, year DESC, created_at DESC;
