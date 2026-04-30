"""rename dataset_documents.metadata to doc_metadata

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-30 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("dataset_documents", "metadata", new_column_name="doc_metadata")


def downgrade() -> None:
    op.alter_column("dataset_documents", "doc_metadata", new_column_name="metadata")
