"""Add grade report table

Revision ID: 395f7e014eef
Revises: dcccada31cf2
Create Date: 2024-07-09 19:28:42.850654+00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '395f7e014eef'
down_revision = 'dcccada31cf2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('grade_report',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('average', sa.Float(), nullable=False),
    sa.Column('median', sa.Float(), nullable=False),
    sa.Column('minimum', sa.Float(), nullable=False),
    sa.Column('maximum', sa.Float(), nullable=False),
    sa.Column('stdev', sa.Float(), nullable=False),
    sa.Column('scores', sa.ARRAY(sa.Float()), nullable=False),
    sa.Column('total_points', sa.Float(), nullable=False),
    sa.Column('num_passing', sa.Integer(), nullable=False),
    sa.Column('num_submitted', sa.Integer(), nullable=False),
    sa.Column('num_students', sa.Integer(), nullable=False),
    sa.Column('master_notebook_content', sa.Text, nullable=False),
    sa.Column('otter_config_zip', sa.LargeBinary, nullable=False),
    sa.Column('created_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('assignment_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['assignment_id'], ['assignment.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_grade_report_id'), 'grade_report', ['id'], unique=False)
    op.add_column('submission', sa.Column('graded', sa.Boolean(), server_default='f', nullable=False))
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_grade_report_id'), table_name='grade_report')
    op.drop_table('grade_report')
    op.drop_column('submission', 'graded')
    # ### end Alembic commands ###
