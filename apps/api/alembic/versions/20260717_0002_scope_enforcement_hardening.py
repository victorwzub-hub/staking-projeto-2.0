"""Harden scope-enforcement concurrency invariants.

Revision ID: 20260717_0002
Revises: 20260716_0001
Create Date: 2026-07-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260717_0002"
down_revision: str | None = "20260716_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Old pending records must not block a new invitation after their expiry time.
    op.execute(
        """
        UPDATE invitations
        SET status = 'expired', updated_at = now(), version = version + 1
        WHERE status = 'pending' AND expires_at <= now()
        """
    )
    # A race in the previous implementation could leave more than one usable token.
    # Preserve the newest invitation and revoke older duplicates before enforcing uniqueness.
    op.execute(
        """
        WITH ranked AS (
          SELECT id,
                 row_number() OVER (
                   PARTITION BY tenant_id, normalized_email
                   ORDER BY created_at DESC, id DESC
                 ) AS position
          FROM invitations
          WHERE status = 'pending'
        )
        UPDATE invitations AS invitation
        SET status = 'revoked',
            revoked_at = COALESCE(invitation.revoked_at, now()),
            updated_at = now(),
            version = invitation.version + 1
        FROM ranked
        WHERE invitation.id = ranked.id AND ranked.position > 1
        """
    )
    op.create_index(
        "uq_invitations_pending_tenant_email",
        "invitations",
        ["tenant_id", "normalized_email"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("uq_invitations_pending_tenant_email", table_name="invitations")
