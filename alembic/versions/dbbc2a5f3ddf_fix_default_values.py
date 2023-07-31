"""Fix default values.

Revision ID: dbbc2a5f3ddf
Revises: 8dd5af23b1f2
Create Date: 2023-07-31 23:44:59.541567+00:00

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'dbbc2a5f3ddf'
down_revision = '8dd5af23b1f2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('assignment', 'created_date',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=sa.text('CURRENT_TIMESTAMP'),
               existing_nullable=True)
    op.alter_column('assignment', 'last_modified_date',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=sa.text('CURRENT_TIMESTAMP'),
               existing_nullable=True)
    op.alter_column('extra_time', 'deferred_time',
               existing_type=postgresql.INTERVAL(),
               server_default='0',
               existing_nullable=True)
    op.alter_column('extra_time', 'extra_time',
               existing_type=postgresql.INTERVAL(),
               server_default='0',
               existing_nullable=True)
    op.alter_column('student', 'base_extra_time',
               existing_type=postgresql.INTERVAL(),
               server_default='0',
               existing_nullable=True)
    op.alter_column('submission', 'submission_time',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=sa.text('CURRENT_TIMESTAMP'),
               existing_nullable=True)
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.alter_column('submission', 'submission_time',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=None,
               existing_nullable=True)
    op.alter_column('student', 'base_extra_time',
               existing_type=postgresql.INTERVAL(),
               server_default=None,
               existing_nullable=True)
    op.alter_column('extra_time', 'extra_time',
               existing_type=postgresql.INTERVAL(),
               server_default=None,
               existing_nullable=True)
    op.alter_column('extra_time', 'deferred_time',
               existing_type=postgresql.INTERVAL(),
               server_default=None,
               existing_nullable=True)
    op.alter_column('assignment', 'last_modified_date',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=None,
               existing_nullable=True)
    op.alter_column('assignment', 'created_date',
               existing_type=postgresql.TIMESTAMP(timezone=True),
               server_default=None,
               existing_nullable=True)
    # ### end Alembic commands ###