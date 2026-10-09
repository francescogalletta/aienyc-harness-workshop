-- Step 2: what the person said about their real situation, kept for later (SPEC 5.5).

CREATE TABLE notes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,        -- UTC, ISO 8601
    session_id  TEXT NOT NULL,
    step_id     TEXT NOT NULL,        -- the brief step being built when it was said
    text        TEXT NOT NULL         -- what the person typed, stripped
);
