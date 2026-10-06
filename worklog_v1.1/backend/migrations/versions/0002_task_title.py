"""log_tasks.title: optional TASK name

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nullable 컬럼 추가만 하므로 기존 일지/TASK 데이터는 그대로 보존된다(기존 TASK 의 이름은 NULL = 본문 첫 줄 요약 사용).
    with op.batch_alter_table('log_tasks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('title', sa.String(length=200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('log_tasks', schema=None) as batch_op:
        batch_op.drop_column('title')
