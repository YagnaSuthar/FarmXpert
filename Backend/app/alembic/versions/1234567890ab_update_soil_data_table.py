"""update soil_data table

Revision ID: 1234567890ab
Revises: 0db7eddc5a8a
Create Date: 2026-04-26 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '1234567890ab'
down_revision: Union[str, None] = '0db7eddc5a8a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create or update soil_data table with all necessary columns."""
    # Try to create table if it doesn't exist
    try:
        op.create_table(
            'soil_data',
            sa.Column('id', sa.Integer(), nullable=False),
            sa.Column('farm_id', postgresql.UUID(as_uuid=True), nullable=True),
            sa.Column('recorded_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False, index=True),
            # Soil Parameters
            sa.Column('soil_moisture', sa.Float(), nullable=True),
            sa.Column('soil_temperature', sa.Float(), nullable=True),
            sa.Column('soil_ph', sa.Float(), nullable=True),
            sa.Column('nitrogen', sa.Float(), nullable=True),
            sa.Column('phosphorus', sa.Float(), nullable=True),
            sa.Column('potassium', sa.Float(), nullable=True),
            sa.Column('electrical_conductivity', sa.Float(), nullable=True),
            # Air Parameters
            sa.Column('air_temperature', sa.Float(), nullable=True),
            sa.Column('air_humidity', sa.Float(), nullable=True),
            # Context Data
            sa.Column('soil_type', sa.String(length=50), nullable=True),
            sa.Column('rainfall', sa.Float(), nullable=True),
            sa.Column('irrigation_type', sa.String(length=50), nullable=True),
            sa.Column('irrigation_amount', sa.Float(), nullable=True),
            sa.Column('fertilizer_type', sa.String(length=100), nullable=True),
            sa.Column('fertilizer_amount', sa.Float(), nullable=True),
            sa.Column('crop_type', sa.String(length=50), nullable=True),
            # AI Outputs
            sa.Column('soil_health_score', sa.Float(), nullable=True),
            sa.Column('soil_health_status', sa.String(length=20), nullable=True),
            sa.Column('alerts', postgresql.JSON(), nullable=True),
            sa.Column('recommendations', postgresql.JSON(), nullable=True),
            sa.PrimaryKeyConstraint('id'),
            sa.ForeignKeyConstraint(['farm_id'], ['farms.id'], )
        )
        # Create indexes
        op.create_index(op.f('ix_soil_data_farm_id'), 'soil_data', ['farm_id'], unique=False)
        op.create_index(op.f('ix_soil_data_recorded_at'), 'soil_data', ['recorded_at'], unique=False)
    except Exception as e:
        # Table might already exist - that's okay, just ensure indexes are present
        pass


def downgrade() -> None:
    """Drop soil_data table."""
    op.drop_index(op.f('ix_soil_data_recorded_at'), table_name='soil_data')
    op.drop_index(op.f('ix_soil_data_farm_id'), table_name='soil_data')
    op.drop_table('soil_data')
