"""知识库来源

Revision ID: 7da49d2f0262
Revises: b5486c6150fb
Create Date: 2026-11-24 23:50:55.313111

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7da49d2f0262'
down_revision: Union[str, Sequence[str], None] = 'b5486c6150fb'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """source_dir 改名 source：除了文件夹，还可以是 shop（从接入方的帮助文章同步）。"""
    op.alter_column("knowledge_bases", "source_dir", new_column_name="source")


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column("knowledge_bases", "source", new_column_name="source_dir")
