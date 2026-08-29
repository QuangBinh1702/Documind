"""Chia sẻ một phiên hội thoại chỉ đọc — US-039.

Mô hình quyền ở đây khác hẳn phần còn lại của hệ thống, nên nó đáng được nói rõ.

**Đọc thì không cần tài khoản, hỏi thì cần.** Token trong đường liên kết mở
đúng một phiên hội thoại và các nguồn đứng sau nó, cho bất kỳ ai cầm nó. Nhưng
một lượt hỏi mới thì đòi đăng nhập, vì nó phải thuộc về một ai đó: câu hỏi ấy
đi vào lịch sử của **người hỏi** và tiêu hạn mức của **người hỏi**.

Đó là chỗ thiết kế này rời khỏi US-039 AC-4 — xem quyết định 0004. Bản gốc tính
mọi chi phí cho chủ notebook vì "không thể tính cho một người không có tài
khoản". Khi người xem buộc phải đăng nhập mới hỏi được thì lý do ấy không còn,
và tính cho người thực sự bấm nút là cách chia chi phí đúng hơn.

**Người xem không thấy bộ nhớ đệm của chủ sở hữu.** `external_answer_cache`
chứa những câu chủ sở hữu đã hỏi ra ngoài, và bản thân danh sách câu hỏi ấy là
thông tin riêng tư. Đường chia sẻ vì vậy bỏ qua cache của chủ sở hữu hoàn toàn.

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
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.chat import ChatSession
from app.models.knowledge import Notebook, ShareLink

__all__ = [
    "DaMo",
    "ShareError",
    "lay_lien_ket",
    "lay_notebook_chia_se",
    "tao_hoac_lay",
    "thu_hoi",
]

log = logging.getLogger(__name__)

# 32 byte ngẫu nhiên → 43 ký tự URL-safe, thoả AC-1 (≥ 32 ký tự).
_SO_BYTE = 32


class ShareError(Exception):
    pass


@dataclass(frozen=True)
class DaMo:
    """Những gì một token mở ra."""

    notebook: Notebook
    owner_id: uuid.UUID
    #: Phiên được chia sẻ. `None` với liên kết mức notebook — xem `ShareLink`.
    phien: ChatSession | None


def _tim(
    session: Session, notebook_id: uuid.UUID, session_id: uuid.UUID | None
) -> ShareLink | None:
    """Liên kết của đúng cặp (notebook, phiên).

    `is_(None)` chứ không `== None`: với `session_id` để trống, `= NULL` trong
    SQL không bao giờ đúng, nên phép so sánh thông thường sẽ không tìm thấy liên
    kết mức notebook nào và cứ mỗi lần bấm lại cấp một token mới.
    """
    dieu_kien = (
        ShareLink.session_id.is_(None)
        if session_id is None
        else ShareLink.session_id == session_id
    )
    return session.scalar(
        select(ShareLink).where(ShareLink.notebook_id == notebook_id, dieu_kien)
    )


def lay_lien_ket(
    session: Session, notebook: Notebook, session_id: uuid.UUID | None
) -> ShareLink | None:
    """Liên kết còn hiệu lực của một phiên, nếu có."""
    lien_ket = _tim(session, notebook.id, session_id)
    return lien_ket if lien_ket is not None and lien_ket.con_hieu_luc else None


def tao_hoac_lay(
    session: Session, notebook: Notebook, session_id: uuid.UUID | None = None
) -> ShareLink:
    """Liên kết chia sẻ của một phiên, tạo mới nếu chưa có.

    Bấm "Chia sẻ" lần thứ hai trên cùng một phiên trả về **đúng liên kết cũ**
    thay vì sinh cái mới. Sinh mới mỗi lần bấm sẽ âm thầm vô hiệu hoá liên kết
    đã phát đi — người dùng bấm để xem lại link, và mất quyền truy cập của cả
    nhóm.

    Liên kết đã thu hồi thì được cấp token mới: thu hồi rồi chia sẻ lại là một ý
    định rõ ràng, khác hẳn với bấm nhầm hai lần.
    """
    lien_ket = _tim(session, notebook.id, session_id)

    if lien_ket is None:
        lien_ket = ShareLink(
            notebook_id=notebook.id,
            session_id=session_id,
            token=secrets.token_urlsafe(_SO_BYTE),
        )
        session.add(lien_ket)
        session.flush()
        log.info("Tạo liên kết chia sẻ cho phiên %s", session_id or "(cả notebook)")
    elif not lien_ket.con_hieu_luc:
        lien_ket.token = secrets.token_urlsafe(_SO_BYTE)
        lien_ket.revoked_at = None
        session.flush()
        log.info("Cấp lại liên kết chia sẻ cho phiên %s", session_id or "(cả notebook)")

    return lien_ket


def thu_hoi(
    session: Session, notebook: Notebook, session_id: uuid.UUID | None = None
) -> bool:
    """Thu hồi liên kết. Trả về `True` nếu có gì đó để thu hồi."""
    lien_ket = _tim(session, notebook.id, session_id)
    if lien_ket is None or not lien_ket.con_hieu_luc:
        return False

    lien_ket.revoked_at = datetime.now(UTC)
    session.flush()
    log.info("Thu hồi liên kết chia sẻ của phiên %s", session_id or "(cả notebook)")
    return True


def lay_notebook_chia_se(session: Session, token: str) -> DaMo:
    """Những gì đứng sau một token.

    Ném `ShareError` cho token sai, token đã thu hồi, notebook đã xoá và phiên
    đã xoá — cả bốn ca đều thành **404** ở tầng API. Phân biệt chúng sẽ cho biết
    một token từng tồn tại, tức là xác nhận cho người đang thử token ngẫu nhiên
    rằng họ đang đi đúng hướng.
    """
    if not token or len(token) < 20:
        raise ShareError("Liên kết không hợp lệ.")

    lien_ket = session.scalar(select(ShareLink).where(ShareLink.token == token))
    if lien_ket is None or not lien_ket.con_hieu_luc:
        raise ShareError("Liên kết không tồn tại hoặc đã bị thu hồi.")

    nb = session.get(Notebook, lien_ket.notebook_id)
    if nb is None:
        raise ShareError("Liên kết không tồn tại hoặc đã bị thu hồi.")

    phien: ChatSession | None = None
    if lien_ket.session_id is not None:
        phien = session.get(ChatSession, lien_ket.session_id)
        # Khoá ngoại có ON DELETE CASCADE nên ca này không xảy ra qua đường
        # thông thường. Vẫn kiểm, vì phương án còn lại là một liên kết "hợp lệ"
        # mở ra một phiên rỗng mà không ai giải thích được.
        if phien is None or phien.notebook_id != nb.id:
            raise ShareError("Liên kết không tồn tại hoặc đã bị thu hồi.")

    return DaMo(notebook=nb, owner_id=nb.user_id, phien=phien)
