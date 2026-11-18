"""Initial schema baseline.

Revision ID: 0001
Revises:
Create Date: 2026-11-17

The baseline intentionally creates no domain tables. Phase 2 introduces the
energy-domain schema with its own reviewed migrations.
"""

from collections.abc import Sequence

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
