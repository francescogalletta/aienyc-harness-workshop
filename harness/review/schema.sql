-- Layer 5: review (SPEC 7.4). Applied on every connect while layer 5 is on.

CREATE TABLE IF NOT EXISTS review_passes (   -- one row per reviewer pass, written when it finishes
    id           INTEGER PRIMARY KEY AUTOINCREMENT,   -- the pass number the challenges carry
    ts           TEXT NOT NULL,
    conversation TEXT NOT NULL,
    trigger      TEXT NOT NULL,       -- "loaded" | "accepted" | "plan_changed" | "assumptions"
    lookups      INTEGER NOT NULL,    -- lookups the reviewer asked for
    kept         INTEGER NOT NULL,
    dropped      INTEGER NOT NULL,
    seconds      REAL NOT NULL,
    assumption_mark INTEGER NOT NULL DEFAULT 0   -- the highest assumption id there was when the pass began
);

CREATE TABLE IF NOT EXISTS challenges (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,   -- shown as "c<id>"
    ts           TEXT NOT NULL,
    conversation TEXT NOT NULL,
    pass         INTEGER NOT NULL,    -- review_passes.id
    step_id      TEXT NOT NULL,
    kind         TEXT NOT NULL,       -- "challenge" | "question"
    title        TEXT NOT NULL,       -- at most 45 characters
    concern      TEXT NOT NULL,
    proposal     TEXT NOT NULL,       -- "" for a question
    change       TEXT NOT NULL,       -- "plan" | "assumption" | "input" | "build_step" | "replace_step" | "none"
    impact       TEXT NOT NULL,       -- "high" | "medium" | "low"
    rank         INTEGER NOT NULL,    -- 1, 2, 3 within its pass
    sources      TEXT NOT NULL,       -- JSON list of {"title", "url"}: addresses a lookup of the pass returned
    status       TEXT NOT NULL,       -- "open" | "used" | "dismissed"
    thread_id    TEXT NOT NULL        -- "t<n>", the review thread
);
