"""Fix opportunity_id nullable constraint

Revision ID: 003
Revises: 002
Create Date: 2025-01-06 10:20:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None

def upgrade():
    """Make opportunity_id nullable in user_notifications table"""
    # SQLite doesn't support ALTER COLUMN directly, so we need to recreate the table
    with op.batch_alter_table('user_notifications', schema=None) as batch_op:
        batch_op.alter_column('opportunity_id',
                              existing_type=sa.INTEGER(),
                              nullable=True)
        batch_op.alter_column('channel',
                              existing_type=sa.VARCHAR(20),
                              nullable=False)
        batch_op.alter_column('title',
                              existing_type=sa.VARCHAR(200),
                              nullable=False)
        batch_op.alter_column('message',
                              existing_type=sa.TEXT(),
                              nullable=False)

def downgrade():
    """Revert opportunity_id to not nullable"""
    with op.batch_alter_table('user_notifications', schema=None) as batch_op:
        batch_op.alter_column('opportunity_id',
                              existing_type=sa.INTEGER(),
                              nullable=False)
        batch_op.alter_column('channel',
                              existing_type=sa.VARCHAR(20),
                              nullable=True)
        batch_op.alter_column('title',
                              existing_type=sa.VARCHAR(200),
                              nullable=True)
        batch_op.alter_column('message',
                              existing_type=sa.TEXT(),
                              nullable=True)