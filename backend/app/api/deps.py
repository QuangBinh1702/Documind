"""Dependency dùng chung cho tầng API.

Điểm quan trọng nhất ở đây là `notebook_cua_toi`: nó là chỗ **duy nhất** mọi
endpoint đi qua để lấy một notebook, và nó trả về **404** khi notebook thuộc về
người khác — không phải 403.

Đó là yêu cầu của US-005 AC-5, và lý do đáng nhắc lại: 403 xác nhận tài nguyên
**có tồn tại**, chỉ là bạn không được vào. Ai muốn dò xem người khác có notebook
nào chỉ cần thử id cho tới khi thấy 403 thay vì 404. Với 404, hai ca "không tồn
tại" và "không phải của bạn" không phân biệt được từ bên ngoài.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.models.base import session_scope
from app.models.knowledge import Notebook, User
from app.services.auth import AuthError, nguoi_dung_tu_token

__all__ = ["CurrentUser", "DbSession", "notebook_cua_toi"]


def get_session() -> Iterator[Session]:
    with session_scope() as s:
        yield s


DbSession = Annotated[Session, Depends(get_session)]


def _token(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Chưa đăng nhập.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[7:].strip()


def current_user(
    session: DbSession,
    authorization: Annotated[str | None, Header()] = None,
) -> User:
    try:
        return nguoi_dung_tu_token(session, _token(authorization))
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc


CurrentUser = Annotated[User, Depends(current_user)]


def notebook_cua_toi(session: Session, user: User, notebook_id: uuid.UUID) -> Notebook:
    """Lấy notebook của chính người đang đăng nhập, hoặc 404.

    Không tách thành hai nhánh "không tìm thấy" và "không có quyền" — xem chú
    thích đầu tệp.
    """
    nb = session.get(Notebook, notebook_id)
    if nb is None or nb.user_id != user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy notebook."
        )
    return nb
