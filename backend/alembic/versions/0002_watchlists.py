"""Persistent topic watches and immutable research snapshots."""
from alembic import op
import sqlalchemy as sa
revision = "0002_watchlists"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("watchlists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("report_id", sa.String(36), nullable=False),
        sa.Column("topic", sa.Text(), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("frequency", sa.String(12), nullable=False),
        sa.Column("paused", sa.Integer(), nullable=False),
        sa.Column("unread", sa.Integer(), nullable=False),
        sa.Column("next_check", sa.Float(), nullable=False),
        sa.Column("last_check", sa.Float(), nullable=False),
        sa.Column("active_run_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.UniqueConstraint("user_id", "report_id", name="uq_watch_user_report"))
    op.create_index("ix_watchlists_user_id", "watchlists", ["user_id"])
    op.create_index("ix_watchlists_next_check", "watchlists", ["next_check"])
    op.create_table("watchlist_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("watchlist_id", sa.String(36), sa.ForeignKey("watchlists.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("created_at", sa.Float(), nullable=False),
        sa.Column("finished_at", sa.Float(), nullable=True),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("changes", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=False))
    op.create_index("ix_watchlist_runs_watchlist_id", "watchlist_runs", ["watchlist_id"])

def downgrade():
    op.drop_table("watchlist_runs")
    op.drop_table("watchlists")
