-- Step 4: what the person decided in a conversation (SPEC 8.1).

CREATE TABLE decisions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,        -- UTC, ISO 8601
    session_id  TEXT NOT NULL,        -- the conversation
    kind        TEXT NOT NULL,        -- 'assumptions' | 'judgment' | 'build'
    step_id     TEXT,                 -- the step it belongs to, or NULL
    question    TEXT NOT NULL,        -- the block shown, exactly
    options     TEXT NOT NULL,        -- JSON list of the options shown; [] for a yes or no
    choice      TEXT NOT NULL,        -- 'yes' or 'no'; for a judgment '1' to '4' or 'something else'
    words       TEXT NOT NULL,        -- what the person typed, stripped
    runs        TEXT NOT NULL         -- JSON list of the calc_runs ids it rested on
);
