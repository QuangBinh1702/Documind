"""Sua thu tu tin nhan trong mot phien hoi thoai.

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-22

Van de
------
`chat_messages` duoc sap xep theo `created_at`, mac dinh la `now()`. Trong
PostgreSQL, `now()` tra ve **thoi diem bat dau transaction**, khong phai thoi
diem thuc thi cau lenh.

Mot luot hoi dap luu ca cau hoi lan cau tra loi trong CUNG mot transaction, nen
ca hai nhan dung mot timestamp. Pha hoa bang `id` khong giup gi vi `id` la UUID
ngau nhien. Ket qua: cau tra loi co the hien thi truoc cau hoi, va loi nay
khong on dinh — no chi lo ra o mot so lan chay.

Vi sao khong dung clock_timestamp()
-----------------------------------
`clock_timestamp()` tra ve thoi gian thuc va tang dan trong transaction, nen no
sua duoc phan lon truong hop. Nhung do phan giai chi la micro giay, va hai lenh
INSERT lien tiep van co the roi vao cung mot micro giay — dieu thuc su xay ra
khi chay test voi mo hinh ngon ngu gia tra loi gan nhu tuc thi.

Cach sua
--------
Them cot `seq BIGSERIAL`. Thu tu tin nhan trong mot phien BAN CHAT la thu tu
chen, va mot chuoi tang dan bieu dien dung dieu do — khong phu thuoc dong ho,
khong the hoa. Timestamp van duoc giu de hien thi va thong ke.
"""

from __future__ import annotations

from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE chat_messages ADD COLUMN seq BIGSERIAL")
    op.execute("CREATE INDEX idx_messages_seq ON chat_messages (session_id, seq)")

    # Chi muc cu sap theo created_at khong con duoc dung de sap xep nua.
    op.execute("DROP INDEX IF EXISTS ix_chat_messages_session_id_created_at")

    # created_at van dung cho hien thi va thong ke, nen van nen chinh xac.
    op.execute(
        "ALTER TABLE chat_messages "
        "ALTER COLUMN created_at SET DEFAULT clock_timestamp()"
    )
    op.execute(
        "ALTER TABLE external_call_log "
        "ALTER COLUMN called_at SET DEFAULT clock_timestamp()"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_messages_seq")
    op.execute("ALTER TABLE chat_messages DROP COLUMN IF EXISTS seq")
    op.execute("ALTER TABLE chat_messages ALTER COLUMN created_at SET DEFAULT now()")
    op.execute("ALTER TABLE external_call_log ALTER COLUMN called_at SET DEFAULT now()")
