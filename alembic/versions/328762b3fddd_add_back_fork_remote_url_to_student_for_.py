"""Add back fork_remote_url to student for purposes of grading

Revision ID: 328762b3fddd
Revises: 0845bee5c145
Create Date: 2024-04-25 20:08:55.775700+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '328762b3fddd'
down_revision = '0845bee5c145'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('student', sa.Column('fork_remote_url', sa.Text(), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('student', 'fork_remote_url')
    # ### end Alembic commands ###
