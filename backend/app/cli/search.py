"""Truy xuất từ dòng lệnh — quan sát bộ não trước khi có giao diện.

    python -m app.cli.search "chương trình đào tạo được xây dựng thế nào?"
    python -m app.cli.search "TCVN 5945" --notebook "Quy chế" --explain

Hiển thị thứ hạng của từng nhánh cạnh điểm RRF, nên nhìn được **vì sao** một
đoạn được chọn — thứ cần cho gỡ lỗi và cho phần phân tích ở Chương 5.
"""

from __future__ import annotations

import argparse
import logging
import sys

from sqlalchemy import select

from app.adapters.embedding import get_embedding_provider
from app.models.base import session_scope
from app.models.knowledge import Notebook, User
from app.services.retrieval import retrieve
from app.settings import settings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.search",
        description="Truy xuất lai trên kho tri thức DocuMind.",
    )
    parser.add_argument("question", help="Câu hỏi")
    parser.add_argument("--notebook", "-n", default=None, help="Tên notebook")
    parser.add_argument("--owner", default="cli@documind.local")
    parser.add_argument("--top", "-k", type=int, default=10, help="Số kết quả hiển thị")
    parser.add_argument(
        "--explain", "-e", action="store_true", help="Hiện thứ hạng từng nhánh"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-5s %(message)s",
    )

    embedder = get_embedding_provider()

    with session_scope() as session:
        user = session.scalar(select(User).where(User.email == args.owner))
        if user is None:
            print(f"Không có tài khoản {args.owner}. Nạp tài liệu trước:", file=sys.stderr)
            print("  python -m app.cli.ingest <tệp> --notebook <tên>", file=sys.stderr)
            return 1

        stmt = select(Notebook).where(Notebook.user_id == user.id)
        if args.notebook:
            stmt = stmt.where(Notebook.title == args.notebook)
        notebook = session.scalar(stmt.order_by(Notebook.updated_at.desc()))
        if notebook is None:
            print(f"Không tìm thấy notebook cho {args.owner}.", file=sys.stderr)
            return 1

        branches = []
        if settings.retrieval_vector_enabled:
            branches.append("vector")
        if settings.retrieval_bm25_enabled:
            branches.append("từ khoá")

        print(f'Câu hỏi  : "{args.question}"')
        print(f"Notebook : {notebook.title}")
        print(f"Nhánh    : {' + '.join(branches) or '(không có nhánh nào bật!)'}")
        print(f"RRF k    : {settings.rrf_k}")
        for w in settings.warnings():
            print(f"\n  [!] {w}")
        print()

        result = retrieve(
            session,
            args.question,
            notebook_id=notebook.id,
            embedder=embedder,
            owner_id=user.id,
        )

    print(
        f"Ứng viên : vector {result.vector_count} · "
        f"từ khoá {result.fulltext_count} · sau RRF {len(result)}"
    )
    if not result.chunks:
        print("\nKhông tìm thấy đoạn nào.")
        return 0

    print()
    for i, sc in enumerate(result.chunks[: args.top], 1):
        c = sc.candidate
        where = f"trang {c.page_no}" if c.page_no else "—"
        print(f"[{i}] RRF {sc.rrf_score:.5f}  ·  {where}  ·  chunk {c.chunk_id}")
        if args.explain:
            detail = "  ".join(f"{b}=#{r}" for b, r in sorted(sc.ranks.items()))
            print(f"     hạng: {detail}")
        if c.heading_path:
            print(f"     {c.heading_path}")
        snippet = " ".join(c.content.split())[:150]
        print(f"     {snippet}…")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
