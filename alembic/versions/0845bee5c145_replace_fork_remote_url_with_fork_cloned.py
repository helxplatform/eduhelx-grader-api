"""Replace fork_remote_url with fork_cloned

Revision ID: 0845bee5c145
Revises: 675a2d5b61b4
Create Date: 2024-03-27 22:44:16.211381+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '0845bee5c145'
down_revision = '675a2d5b61b4'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('student', sa.Column('fork_cloned', sa.Boolean(), server_default='0', nullable=True))
    op.drop_column('student', 'fork_remote_url')
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('student', sa.Column('fork_remote_url', sa.TEXT(), server_default=sa.text("''::text"), autoincrement=False, nullable=False))
    op.drop_column('student', 'fork_cloned')
    # ### end Alembic commands ###
