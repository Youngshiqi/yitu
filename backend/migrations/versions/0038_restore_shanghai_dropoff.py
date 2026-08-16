"""Restore the retained Shanghai station drop-off service area."""

from collections.abc import Sequence

from alembic import op

revision: str = "0038"
down_revision: str | None = "0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        INSERT INTO service_areas (id, district_code, service_type, station_id, version)
        SELECT gen_random_uuid(), '310105', 'STATION_DROP_OFF', id, 1
        FROM stations
        WHERE code = 'SHS-001'
          AND NOT EXISTS (
              SELECT 1 FROM service_areas
              WHERE district_code = '310105' AND service_type = 'STATION_DROP_OFF'
          )
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM service_areas
        WHERE district_code = '310105'
          AND service_type = 'STATION_DROP_OFF'
          AND station_id = (SELECT id FROM stations WHERE code = 'SHS-001')
        """
    )
