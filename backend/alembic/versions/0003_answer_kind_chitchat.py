"""Cho phep answer_kind = 'chitchat'.

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-23

Van de
------
US-066 them mot loai cau tra loi moi: `chitchat` — loi chao va cau hoi ve chinh
tro ly, di thang khong qua truy xuat. `AnswerKind` trong ma nguon da co gia tri
do, nhung CHECK constraint tu migration 0001 thi chua:

    CHECK (answer_kind IN ('grounded','no_answer','external','cached_external'))

Hau qua: mo hinh tra loi dung, nguoi dung doc duoc cau tra loi tren man hinh,
roi buoc **luu tin nhan** do vo voi `CheckViolation`. Cau tra loi bien mat khoi
lich su hoi thoai, va giao dien nhan mot loi ngay sau khi vua hien mot cau tra
loi hoan chinh.

Day la lan thu hai cung mot kieu loi: worker cung tung dat `sources.status` sang
mot gia tri ngoai danh sach cho phep. Bai hoc chung — **bo tu vung nam trong
luoc do la mot hop dong**, va them mot gia tri vao `Literal` cua Python khong tu
dong mo rong hop dong do.

Cach sua
--------
Bo constraint cu, dat lai kem 'chitchat'. Khong dung dinh dang ENUM: them gia
tri vao ENUM trong PostgreSQL kho lui lai hon nhieu so voi mot CHECK.
"""

from __future__ import annotations

from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_TEN = "chat_messages_answer_kind_check"

_CU = "('grounded','no_answer','external','cached_external')"
_MOI = "('grounded','no_answer','external','cached_external','chitchat')"


def upgrade() -> None:
    op.execute(f"ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS {_TEN}")
    op.execute(
        f"ALTER TABLE chat_messages ADD CONSTRAINT {_TEN} "
        f"CHECK (answer_kind IN {_MOI})"
    )


def downgrade() -> None:
    # Lui lai thi phai don du lieu truoc, neu khong constraint cu se tu choi
    # chinh nhung dong da ghi trong luc no chua ton tai.
    op.execute("DELETE FROM chat_messages WHERE answer_kind = 'chitchat'")
    op.execute(f"ALTER TABLE chat_messages DROP CONSTRAINT IF EXISTS {_TEN}")
    op.execute(
        f"ALTER TABLE chat_messages ADD CONSTRAINT {_TEN} "
        f"CHECK (answer_kind IN {_CU})"
    )
