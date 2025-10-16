"""Add dollar-based profit calculations to arbitrage opportunities

Revision ID: 005
Revises: 004
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None

def upgrade():
    # Add new dollar-based calculation columns
    op.add_column('arbitrage_opportunities', sa.Column('raw_price_difference', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('arbitrage_opportunities', sa.Column('profit_on_500', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('arbitrage_opportunities', sa.Column('profit_on_1000', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('arbitrage_opportunities', sa.Column('profit_on_5000', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('arbitrage_opportunities', sa.Column('profit_on_10000', sa.Float(), nullable=False, server_default='0.0'))
    op.add_column('arbitrage_opportunities', sa.Column('min_investment_required', sa.Float(), nullable=False, server_default='0.0'))

def downgrade():
    # Remove the new columns
    op.drop_column('arbitrage_opportunities', 'min_investment_required')
    op.drop_column('arbitrage_opportunities', 'profit_on_10000')
    op.drop_column('arbitrage_opportunities', 'profit_on_5000')
    op.drop_column('arbitrage_opportunities', 'profit_on_1000')
    op.drop_column('arbitrage_opportunities', 'profit_on_500')
    op.drop_column('arbitrage_opportunities', 'raw_price_difference')