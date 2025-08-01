"""add User table

迁移 ID: 9dd95c5e9b4d
父迁移: 8141d1806585
创建时间: 2025-06-11 21:32:26.115012

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9dd95c5e9b4d"
down_revision: str | Sequence[str] | None = "8141d1806585"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = ("muicebot",)


def upgrade(name: str = "") -> None:
    if name:
        return
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table(
        "muicebot_user",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("userid", sa.String(), nullable=False),
        sa.Column("nickname", sa.String(), nullable=True, default="_default"),
        sa.Column("profile", sa.String(), nullable=True, default="_default"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_muicebot_user")),
        info={"bind_key": "muicebot"},
    )
    with op.batch_alter_table("muicebot_msg", schema=None) as batch_op:
        batch_op.add_column(sa.Column("profile", sa.String(), nullable=True, default="_default"))
    op.execute("UPDATE muicebot_msg SET profile = '_default'")

    # ### end Alembic commands ###


def downgrade(name: str = "") -> None:
    if name:
        return
    # ### commands auto generated by Alembic - please adjust! ###
    with op.batch_alter_table("muicebot_msg", schema=None) as batch_op:
        batch_op.drop_column("profile")

    op.drop_table("muicebot_user")
    # ### end Alembic commands ###
