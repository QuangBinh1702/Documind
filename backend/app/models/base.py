"""Lớp cơ sở và phiên làm việc với cơ sở dữ liệu.

Lược đồ là **nguồn sự thật**, không phải các lớp ORM ở đây: migration
`0001_initial_schema.py` viết bằng SQL thô vì có chỉ mục HNSW kèm tham số, GIN
trên tsvector, kiểu vector và citext — những thứ Alembic autogenerate xử lý
kém. Các lớp dưới đây **ánh xạ vào** lược đồ đó và phải khớp với nó.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.settings import settings

__all__ = ["Base", "get_engine", "session_scope"]


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def get_engine():
    global _engine, _Session
    if _engine is None:
        _engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
        _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _engine


@contextmanager
def session_scope() -> Iterator[Session]:
    """Phiên làm việc tự commit khi thành công, tự rollback khi có lỗi."""
    get_engine()
    assert _Session is not None
    session = _Session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
