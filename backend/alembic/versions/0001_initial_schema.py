"""Initial account-owned research schema.

Revision ID: 0001_initial_schema
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("users", sa.Column("id", sa.String(36), primary_key=True), sa.Column("email", sa.String(320), nullable=False, unique=True), sa.Column("password_hash", sa.String(256), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_table("research_history", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("topic", sa.Text(), nullable=False), sa.Column("normalized_topic", sa.Text(), nullable=False), sa.Column("depth", sa.Integer(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False), sa.Column("report", sa.Text(), nullable=False), sa.Column("sources", sa.JSON(), nullable=False), sa.Column("queries_used", sa.JSON(), nullable=False), sa.Column("iterations_completed", sa.Integer(), nullable=False), sa.Column("topic_embedding", sa.JSON(), nullable=False), sa.Column("citation_verification", sa.JSON(), nullable=False), sa.UniqueConstraint("user_id", "normalized_topic", "depth", name="uq_user_topic_depth"))
    op.create_index("ix_research_history_user_id", "research_history", ["user_id"])
    op.create_table("collections", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(80), nullable=False), sa.Column("description", sa.String(240), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True), nullable=False), sa.UniqueConstraint("user_id", "name", name="uq_collection_user_name"))
    op.create_table("tags", sa.Column("id", sa.String(36), primary_key=True), sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False), sa.Column("name", sa.String(48), nullable=False), sa.Column("color", sa.String(7), nullable=False), sa.UniqueConstraint("user_id", "name", name="uq_tag_user_name"))
    op.create_table("report_collections", sa.Column("report_id", sa.String(36), sa.ForeignKey("research_history.id", ondelete="CASCADE"), primary_key=True), sa.Column("collection_id", sa.String(36), sa.ForeignKey("collections.id", ondelete="CASCADE"), primary_key=True))
    op.create_table("report_tags", sa.Column("report_id", sa.String(36), sa.ForeignKey("research_history.id", ondelete="CASCADE"), primary_key=True), sa.Column("tag_id", sa.String(36), sa.ForeignKey("tags.id", ondelete="CASCADE"), primary_key=True))


def downgrade() -> None:
    op.drop_table("report_tags")
    op.drop_table("report_collections")
    op.drop_table("tags")
    op.drop_table("collections")
    op.drop_index("ix_research_history_user_id", table_name="research_history")
    op.drop_table("research_history")
    op.drop_table("users")
