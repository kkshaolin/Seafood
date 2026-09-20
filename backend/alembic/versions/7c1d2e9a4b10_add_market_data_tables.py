"""add_market_data_tables

Revision ID: 7c1d2e9a4b10
Revises: 548341a904e8
Create Date: 2026-09-20 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '7c1d2e9a4b10'
down_revision: Union[str, Sequence[str], None] = '548341a904e8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'market_prices',
        sa.Column('symbol', sa.String(length=24), nullable=False),
        sa.Column('trade_date', sa.Date(), nullable=False),
        sa.Column('asset_type', sa.String(length=10), nullable=False),
        sa.Column('open', sa.Float(), nullable=True),
        sa.Column('high', sa.Float(), nullable=True),
        sa.Column('low', sa.Float(), nullable=True),
        sa.Column('close', sa.Float(), nullable=True),
        sa.Column('adj_close', sa.Float(), nullable=True),
        sa.Column('volume', sa.BigInteger(), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('symbol', 'trade_date'),
    )
    op.create_table(
        'financial_statements',
        sa.Column('symbol', sa.String(length=24), nullable=False),
        sa.Column('period_end', sa.Date(), nullable=False),
        sa.Column('statement', sa.String(length=10), nullable=False),
        sa.Column('line_item', sa.String(length=120), nullable=False),
        sa.Column('value', sa.Float(), nullable=True),
        sa.Column('ingested_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('symbol', 'period_end', 'statement', 'line_item'),
    )
    op.create_table(
        'ingestion_runs',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('dataset', sa.String(length=40), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('records_written', sa.Integer(), server_default='0', nullable=False),
        sa.Column('object_key', sa.Text(), nullable=True),
        sa.Column('detail', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_ingestion_runs_dataset'), 'ingestion_runs', ['dataset'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ingestion_runs_dataset'), table_name='ingestion_runs')
    op.drop_table('ingestion_runs')
    op.drop_table('financial_statements')
    op.drop_table('market_prices')
