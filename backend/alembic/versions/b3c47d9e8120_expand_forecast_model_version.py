"""Allow forecast results to store complete model identifiers."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c47d9e8120"
down_revision: Union[str, Sequence[str], None] = "a2e6a70fcc01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "forecast_results",
        "model_version",
        existing_type=sa.String(length=50),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "forecast_results",
        "model_version",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
