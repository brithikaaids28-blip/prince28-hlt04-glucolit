
"""Add GIN index on documents metadata.

Revision ID: 38174267d419
Revises: 1d1bad238490
"""

from typing import Sequence, Union

from alembic import op

# Revision identifiers.
revision: str = "38174267d419"
down_revision: Union[str, Sequence[str], None] = "1d1bad238490"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create GIN index on documents.metadata."""
    op.create_index(
        "ix_documents_metadata_gin",
        "documents",
        ["metadata"],
        unique=False,
        postgresql_using="gin",
        postgresql_ops={"metadata": "jsonb_path_ops"},
    )


def downgrade() -> None:
    """Remove GIN index."""
    op.drop_index(
        "ix_documents_metadata_gin",
        table_name="documents",
    )
