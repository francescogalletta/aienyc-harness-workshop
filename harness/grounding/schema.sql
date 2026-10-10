-- Layer 1: the plan. Applied on every connect while layer 1 is on; no migration history.

-- Lookups already made (SPEC 3.4): a found term is fetched once and remembered.
-- key is the query, or the standard name, lower-cased with runs of spaces,
-- hyphens and underscores as one space.
CREATE TABLE IF NOT EXISTS lookups (
    key           TEXT PRIMARY KEY,
    query         TEXT NOT NULL,
    name          TEXT NOT NULL,
    definition    TEXT NOT NULL,
    sources       TEXT NOT NULL,      -- JSON list of {"title", "url"}
    origin        TEXT NOT NULL,      -- the researcher that answered
    looked_up_at  TEXT NOT NULL       -- UTC, ISO 8601
);
