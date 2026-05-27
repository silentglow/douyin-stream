import sqlite3


def create_table(conn: sqlite3.Connection) -> None:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS transcribe_runs (
        run_id TEXT PRIMARY KEY,
        asset_id TEXT NOT NULL,
        video_path TEXT NOT NULL,
        account_id TEXT NOT NULL,
        task_id TEXT,
        stage TEXT NOT NULL DEFAULT 'queued',
        record_id TEXT,
        gen_record_id TEXT,
        batch_id TEXT,
        export_task_id TEXT,
        export_url TEXT,
        transcript_path TEXT,
        last_error TEXT,
        error_stage TEXT,
        error_type TEXT,
        created_at DATETIME NOT NULL,
        updated_at DATETIME NOT NULL
    )
    """)


def create_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_transcribe_runs_asset_account ON transcribe_runs(asset_id, account_id, stage)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transcribe_runs_asset_stage ON transcribe_runs(asset_id, stage)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_transcribe_runs_stage_updated ON transcribe_runs(stage, updated_at)")
