"""Chia sẻ notebook chỉ đọc — US-039.

Mô hình quyền ở đây khác hẳn phần còn lại của hệ thống, nên nó đáng được nói rõ.

**Người xem không có tài khoản.** Họ cầm một token trong đường liên kết, và
token đó chỉ mở đúng một notebook. Không có phiên đăng nhập, không có danh tính,
không có gì để nâng quyền lên.

**Mọi chi phí tính cho chủ sở hữu.** Một lượt hỏi từ đường chia sẻ vẫn gọi mô
hình, và lượt gọi ấy tính vào hạn mức của người chia sẻ (AC-4). Nói cách khác:
phát liên kết ra là cho người khác tiêu hạn mức của mình. Đó là lựa chọn đúng —
không thể tính cho một người không có tài khoản — nhưng nó phải rõ ràng ở giao
diện, không phải một bất ngờ khi hết hạn mức.

**Người xem không thấy bộ nhớ đệm của chủ sở hữu.** `external_answer_cache`
chứa những câu chủ sở hữu đã hỏi ra ngoài, và bản thân danh sách câu hỏi ấy là
thông tin riêng tư. Đường chia sẻ vì vậy bỏ qua cache hoàn toàn (AC-4).

Về độ dài token
----------------
32 ký tự sinh bằng `secrets.token_urlsafe(32)` cho ra 43 ký tự và 256 bit ngẫu
nhiên. Đây là thứ **thay thế cho mật khẩu**: ai có nó thì đọc được, nên nó phải
không đoán được, và `random` của Python thì không đủ — `secrets` mới lấy từ
nguồn ngẫu nhiên của hệ điều hành.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.knowledge import Notebook, ShareLink

__all__ = ["ShareError", "lay_notebook_chia_se", "tao_hoac_lay", "thu_hoi"]

log = logging.getLogger(__name__)

# 32 byte ngẫu nhiên → 43 ký tự URL-safe, thoả AC-1 (≥ 32 ký tự).
_SO_BYTE = 32


class ShareError(Exception):
    pass


def tao_hoac_lay(session: Session, notebook: Notebook) -> ShareLink:
    """Liên kết chia sẻ của một notebook, tạo mới nếu chưa có.

    Bấm "Chia sẻ" lần thứ hai trả về **đúng liên kết cũ** thay vì sinh cái mới.
    Sinh mới mỗi lần bấm sẽ âm thầm vô hiệu hoá liên kết đã phát đi — người dùng
    bấm để xem lại link, và mất quyền truy cập của cả nhóm.

    Liên kết đã thu hồi thì được cấp token mới: thu hồi rồi chia sẻ lại là một ý
    định rõ ràng, khác hẳn với bấm nhầm hai lần.
    """
    lien_ket = session.get(ShareLink, notebook.id)

    if lien_ket is None:
        lien_ket = ShareLink(
            notebook_id=notebook.id, token=secrets.token_urlsafe(_SO_BYTE)
        )
        session.add(lien_ket)
        session.flush()
        log.info("Tạo liên kết chia sẻ cho notebook %s", notebook.id)
    elif not lien_ket.con_hieu_luc:
        lien_ket.token = secrets.token_urlsafe(_SO_BYTE)
        lien_ket.revoked_at = None
        session.flush()
        log.info("Cấp lại liên kết chia sẻ cho notebook %s", notebook.id)

    return lien_ket


def thu_hoi(session: Session, notebook: Notebook) -> bool:
    """Thu hồi liên kết. Trả về `True` nếu có gì đó để thu hồi."""
    lien_ket = session.get(ShareLink, notebook.id)
    if lien_ket is None or not lien_ket.con_hieu_luc:
        return False

    lien_ket.revoked_at = datetime.now(UTC)
    session.flush()
    log.info("Thu hồi liên kết chia sẻ của notebook %s", notebook.id)
    return True


def lay_notebook_chia_se(session: Session, token: str) -> tuple[Notebook, uuid.UUID]:
    """Notebook đứng sau một token, kèm id chủ sở hữu.

    Ném `ShareError` cho token sai, token đã thu hồi và notebook đã xoá — cả ba
    ca đều thành **404** ở tầng API. Phân biệt chúng sẽ cho biết một token từng
    tồn tại, tức là xác nhận cho người đang thử token ngẫu nhiên rằng họ đang đi
    đúng hướng.
    """
    if not token or len(token) < 20:
        raise ShareError("Liên kết không hợp lệ.")

    lien_ket = session.scalar(select(ShareLink).where(ShareLink.token == token))
    if lien_ket is None or not lien_ket.con_hieu_luc:
        raise ShareError("Liên kết không tồn tại hoặc đã bị thu hồi.")

    nb = session.get(Notebook, lien_ket.notebook_id)
    if nb is None:
        raise ShareError("Liên kết không tồn tại hoặc đã bị thu hồi.")

    return nb, nb.user_id
