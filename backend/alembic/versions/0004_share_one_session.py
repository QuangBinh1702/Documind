"""Chia sẻ một phiên hội thoại, và phiên có chủ sở hữu riêng.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-29

Vấn đề
------
US-039 dựng liên kết chia sẻ ở mức **notebook**: người xem thấy danh sách nguồn
và hỏi được, nhưng không thấy hội thoại nào. Trong thực tế người ta chia sẻ để
khoe *một đoạn hỏi đáp cụ thể* — người nhận mở liên kết ra thấy màn hình trống
và tưởng tính năng hỏng.

Hai thay đổi lược đồ đi kèm nhau, vì thay đổi thứ nhất không đứng được nếu
thiếu thứ hai.

1. `share_links.session_id`
--------------------------
Liên kết trỏ tới một phiên cụ thể. Khoá chính cũ là `notebook_id`, tức **một
notebook đúng một liên kết** — không còn đủ khi mỗi phiên có liên kết riêng.
Thay bằng khoá thay thế `id`, rồi hai chỉ mục duy nhất từng phần giữ lại đúng
bất biến cũ ở mức mới: tối đa một liên kết cho mỗi phiên, và tối đa một liên
kết mức notebook (`session_id IS NULL`) cho mỗi notebook.

Chỉ mục **từng phần** chứ không phải `UNIQUE (notebook_id, session_id)`: trong
PostgreSQL, NULL không bằng NULL, nên ràng buộc gộp sẽ cho phép vô số liên kết
mức notebook trên cùng một notebook.

2. `chat_sessions.user_id`
--------------------------
Người xem đăng nhập rồi hỏi thì hội thoại đó phải nằm trong lịch sử của **họ**,
không phải của chủ notebook. Điều đó không biểu diễn được với lược đồ cũ: chủ
sở hữu một phiên được **suy ra** từ chủ sở hữu notebook chứa nó, nên hai người
hỏi trong cùng một notebook là không phân biệt được.

`ON DELETE CASCADE` về `users`: xoá tài khoản thì hội thoại của người đó biến
mất, kể cả những hội thoại nằm trong notebook của người khác.

Lưu ý khi lui lại
-----------------
`downgrade()` xoá các phiên **không thuộc chủ notebook** trước khi bỏ cột, vì
lược đồ cũ không có chỗ nào diễn đạt được chúng. Đó là mất dữ liệu thật, nhưng
là mất dữ liệu **có thể nêu tên**: giữ lại thì những hội thoại ấy sẽ âm thầm
đổi chủ sang chủ notebook, mà lộ hội thoại của người khác thì tệ hơn nhiều.
"""

from __future__ import annotations

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Phiên hội thoại có chủ sở hữu riêng ─────────────
    op.execute(
        "ALTER TABLE chat_sessions "
        "ADD COLUMN user_id UUID REFERENCES users(id) ON DELETE CASCADE"
    )
    # Trước migration này, chủ phiên LÀ chủ notebook. Không có dòng nào sót lại:
    # `notebook_id` là NOT NULL và có khoá ngoại, nên phép nối luôn tìm được.
    op.execute(
        """
        UPDATE chat_sessions s
           SET user_id = n.user_id
          FROM notebooks n
         WHERE n.id = s.notebook_id
        """
    )
    op.execute("ALTER TABLE chat_sessions ALTER COLUMN user_id SET NOT NULL")
    op.execute(
        "CREATE INDEX idx_sessions_user ON chat_sessions (user_id, updated_at DESC)"
    )

    # ── Liên kết chia sẻ trỏ tới một phiên ──────────────
    op.execute(
        "ALTER TABLE share_links "
        "ADD COLUMN id UUID NOT NULL DEFAULT gen_random_uuid()"
    )
    op.execute("ALTER TABLE share_links DROP CONSTRAINT share_links_pkey")
    op.execute("ALTER TABLE share_links ADD PRIMARY KEY (id)")
    op.execute(
        "ALTER TABLE share_links "
        "ADD COLUMN session_id UUID REFERENCES chat_sessions(id) ON DELETE CASCADE"
    )
    op.execute("CREATE INDEX idx_share_notebook ON share_links (notebook_id)")
    op.execute(
        "CREATE UNIQUE INDEX uq_share_notebook ON share_links (notebook_id) "
        "WHERE session_id IS NULL"
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_share_session ON share_links (session_id) "
        "WHERE session_id IS NOT NULL"
    )


def downgrade() -> None:
    # Mỗi notebook chỉ giữ được một liên kết ở lược đồ cũ. Giữ liên kết mức
    # notebook nếu có, ngược lại giữ cái cũ nhất — nó là cái nhiều khả năng đã
    # được phát đi cho người khác nhất.
    op.execute(
        """
        DELETE FROM share_links
         WHERE id IN (
               SELECT id
                 FROM (SELECT id,
                              row_number() OVER (
                                  PARTITION BY notebook_id
                                  ORDER BY (session_id IS NULL) DESC, created_at, id
                              ) AS hang
                         FROM share_links) t
                WHERE t.hang > 1
         )
        """
    )
    op.execute("DROP INDEX IF EXISTS uq_share_session")
    op.execute("DROP INDEX IF EXISTS uq_share_notebook")
    op.execute("DROP INDEX IF EXISTS idx_share_notebook")
    op.execute("ALTER TABLE share_links DROP COLUMN session_id")
    op.execute("ALTER TABLE share_links DROP CONSTRAINT share_links_pkey")
    op.execute("ALTER TABLE share_links DROP COLUMN id")
    op.execute("ALTER TABLE share_links ADD PRIMARY KEY (notebook_id)")

    # Xem chú thích đầu tệp: hội thoại của người xem không có chỗ trong lược đồ
    # cũ, và đổi chủ chúng sang chủ notebook là làm lộ dữ liệu.
    op.execute(
        """
        DELETE FROM chat_sessions s
         USING notebooks n
         WHERE n.id = s.notebook_id
           AND s.user_id <> n.user_id
        """
    )
    op.execute("DROP INDEX IF EXISTS idx_sessions_user")
    op.execute("ALTER TABLE chat_sessions DROP COLUMN user_id")
