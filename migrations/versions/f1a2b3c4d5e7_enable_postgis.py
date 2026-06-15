"""enable postgis + geometry columns on reports

Revision ID: f1a2b3c4d5e7
Revises: e9a2b3c4d5f6
Create Date: 2026-06-15 12:00:00.000000

"""
# pylint: disable=invalid-name,no-member
# pylint: disable=import-error,no-member
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry

revision: str = "f1a2b3c4d5e7"
down_revision: Union[str, None] = "e9a2b3c4d5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _postgis_enabled(bind) -> bool:
    row = bind.execute(
        sa.text("SELECT 1 FROM pg_extension WHERE extname = 'postgis'")
    ).fetchone()
    return row is not None


def _ensure_postgis(bind) -> None:
    if _postgis_enabled(bind):
        return
    try:
        op.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    except Exception as exc:
        if _postgis_enabled(bind):
            return
        err = str(exc).lower()
        if "permission denied" in err or "insufficientprivilege" in err:
            raise RuntimeError(
                "PostGIS nao esta habilitado e o usuario do app nao pode CREATE EXTENSION.\n"
                "Peça ao DBA (superuser) no banco:\n"
                "  CREATE EXTENSION IF NOT EXISTS postgis;\n"
                "Depois rode: python scripts/db_migrate.py"
            ) from exc
        raise


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    _ensure_postgis(bind)

    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "geom_point",
                Geometry(geometry_type="POINT", srid=4326),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                "geom_polygon",
                Geometry(geometry_type="POLYGON", srid=4326),
                nullable=True,
            )
        )

    op.execute(
        """
        UPDATE reports
        SET geom_point = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
        WHERE lon IS NOT NULL AND lat IS NOT NULL
        """
    )
    op.execute(
        """
        UPDATE reports
        SET geom_polygon = ST_Buffer(geom_point::geography, 100)::geometry
        WHERE geom_point IS NOT NULL AND geom_polygon IS NULL
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reports_geom_point "
        "ON reports USING GIST (geom_point)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_reports_geom_polygon "
        "ON reports USING GIST (geom_polygon)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return

    op.execute("DROP INDEX IF EXISTS ix_reports_geom_polygon")
    op.execute("DROP INDEX IF EXISTS ix_reports_geom_point")

    with op.batch_alter_table("reports", schema=None) as batch_op:
        batch_op.drop_column("geom_polygon")
        batch_op.drop_column("geom_point")
