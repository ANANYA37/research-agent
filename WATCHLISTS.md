# Research Watchlists

Open a saved Library report, expand **Watch this topic**, choose Weekly or Every 30 days, and start watching. The Watchlists navigation opens all watched topics and indicates unread updates.

Each watch preserves the original report as an immutable baseline. Check now and scheduled checks perform fresh research without the history/semantic-cache shortcut. Each successful check stores a separate snapshot and compares it with the most recent successful snapshot. Failed checks never replace that baseline.

What changed shows line-based text differences and added/removed source URLs. This is not semantic fact verification: wording changes do not establish that the underlying facts changed. Existing Evidence Explorer remains available on Library reports.

## Operation

- Local development: restart the API; init_db creates the new tables.
- Managed deployments: run `alembic upgrade head` from backend using your existing migration process.
- Schedules are stored in the database and checked every 60 seconds while the API process is running. No browser tab or Celery worker is required.
- Keep the API running for unattended checks. Overdue schedules are picked up after restart; offline intervals are not replayed individually.
- Weekly means 7 days; the monthly API value means exactly 30 days. Frequency changes, resume, and manual checks reset the next due time.
- Each process permits two concurrent watchlist checks. Atomic database reservations prevent duplicate checks of the same watch across processes.
- A run has a 15-minute timeout. Interrupted/expired runs are marked failed; use Check now to retry. Automatic retry waits until the next scheduled check.
- Up to 10 watches per account; a 60-second cooldown applies to manual checks. Research uses configured AI/search providers and their credits.
- Pause stops future checks, not one already running. Removal is available after the current check finishes. Removing a watch deletes its snapshots but preserves the Library report.
- Snapshots support reading, source links, and Markdown download. Existing PDF/Word exports remain on Library reports.
- Notifications are in-app badges, not email or push.

## Verification

From backend: `python -B -m unittest test_watchlists -v`.
Tests use an isolated in-memory database and mock research, without calling paid APIs.
