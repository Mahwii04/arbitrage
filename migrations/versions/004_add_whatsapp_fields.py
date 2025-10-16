"""Add WhatsApp fields to notification settings

Revision ID: 003
Revises: 002
Create Date: 2024-01-20 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    """Add WhatsApp fields to notification_settings table"""
    # Check if columns exist before adding them
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_columns = [col['name'] for col in inspector.get_columns('notification_settings')]
    
    with op.batch_alter_table('notification_settings', schema=None) as batch_op:
        # Add WhatsApp enabled field
        if 'whatsapp_enabled' not in existing_columns:
            batch_op.add_column(sa.Column('whatsapp_enabled', sa.Boolean(), nullable=True, default=False))
        
        # Add WhatsApp number field
        if 'whatsapp_number' not in existing_columns:
            batch_op.add_column(sa.Column('whatsapp_number', sa.String(20), nullable=True))
        
        # Add WhatsApp username field
        if 'whatsapp_username' not in existing_columns:
            batch_op.add_column(sa.Column('whatsapp_username', sa.String(100), nullable=True))
    
    # Set default values for existing records
    conn.execute(
        sa.text("UPDATE notification_settings SET whatsapp_enabled = 0 WHERE whatsapp_enabled IS NULL")
    )


def downgrade():
    """Remove WhatsApp fields from notification_settings table"""
    with op.batch_alter_table('notification_settings', schema=None) as batch_op:
        batch_op.drop_column('whatsapp_username')
        batch_op.drop_column('whatsapp_number')
        batch_op.drop_column('whatsapp_enabled')