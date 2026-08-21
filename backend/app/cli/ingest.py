"""Nạp tài liệu vào kho tri thức từ dòng lệnh.

    python -m app.cli.ingest tailieu.pdf --notebook "Quy chế"
    python -m app.cli.ingest eval/dataset/documents --notebook "Quy chế" --recursive

Chạy thẳng `trích xuất → chunk → nhúng → ghi DB`, không qua hàng đợi và không
qua API. Đây là cách đưa dữ liệu thật vào cơ sở dữ liệu để xây và đo phần lõi
RAG trước khi có xác thực, tải tệp và worker (US-021 sẽ dùng lại đúng service
này).
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from app.adapters.embedding import get_embedding_provider
from app.adapters.extract import ExtractionError
from app.models.base import session_scope
from app.services.ingest import SUFFIX_TO_KIND, ingest_file_sync
from app.settings import settings


def _collect(paths: list[str], recursive: bool) -> list[Path]:
    out: list[Path] = []
    for raw in paths:
        p = Path(raw)
        if p.is_dir():
            pattern = "**/*" if recursive else "*"
            out.extend(
                f
                for f in sorted(p.glob(pattern))
                if f.is_file() and f.suffix.lower() in SUFFIX_TO_KIND
            )
        elif p.is_file():
            out.append(p)
        else:
            print(f"  [bỏ qua] không tìm thấy: {raw}", file=sys.stderr)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.ingest",
        description="Nạp tài liệu vào kho tri thức DocuMind.",
    )
    parser.add_argument("paths", nargs="+", help="Tệp hoặc thư mục cần nạp")
    parser.add_argument(
        "--notebook", "-n", default="Mặc định", help="Tên notebook chứa tài liệu"
    )
    parser.add_argument(
        "--owner", default="cli@documind.local", help="Email chủ sở hữu notebook"
    )
    parser.add_argument(
        "--recursive", "-r", action="store_true", help="Duyệt cả thư mục con"
    )
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)-5s %(message)s",
    )

    files = _collect(args.paths, args.recursive)
    if not files:
        print("Không có tệp nào để nạp.", file=sys.stderr)
        print(f"Định dạng hỗ trợ: {', '.join(sorted(SUFFIX_TO_KIND))}", file=sys.stderr)
        return 1

    embedder = get_embedding_provider()

    print(f"Notebook  : {args.notebook}")
    print(f"Nhúng     : {embedder.name} ({embedder.dim} chiều)")
    print(
        f"Chunk     : {settings.chunk_tokens} token, "
        f"chồng lặp {settings.chunk_overlap_ratio:.0%}"
    )
    print(f"Tệp       : {len(files)}")
    for w in settings.warnings():
        print(f"\n  [!] {w}")
    print()

    ok, failed = [], []

    for i, path in enumerate(files, 1):
        print(f"[{i}/{len(files)}] {path.name}")
        try:
            with session_scope() as session:
                result = ingest_file_sync(
                    session,
                    path,
                    notebook_title=args.notebook,
                    embedder=embedder,
                    owner_email=args.owner,
                    on_progress=(lambda m: print(f"        {m}")) if args.verbose else None,
                )
        except ExtractionError as e:
            print(f"        LỖI {e.code}: {e.message_vi}")
            failed.append((path.name, e.code, e.message_vi))
            continue
        except Exception as e:
            print(f"        LỖI {type(e).__name__}: {e}")
            failed.append((path.name, type(e).__name__, str(e)[:120]))
            continue

        flag = "✓" if result.invariant_holds else "✗ INV-1 SAI"
        print(
            f"        {result.chunk_count} đoạn · {result.page_count} trang · "
            f"chất lượng {result.quality.score:.2f} · {result.method} · offset {flag}"
        )
        ok.append(result)

    print()
    print(f"Nạp được {len(ok)}/{len(files)} tệp, tổng {sum(r.chunk_count for r in ok)} đoạn.")

    if failed:
        print(f"\nThất bại {len(failed)}:")
        for name, code, msg in failed:
            print(f"  {name:<45} {code:<24} {msg[:60]}")

    broken = [r for r in ok if not r.invariant_holds]
    if broken:
        print(f"\n[!] {len(broken)} tệp vi phạm bất biến INV-1 — offset không cắt lại đúng.")
        print("    Đây là rủi ro số một của đồ án (SPEC.md §J.6). Dừng lại và điều tra.")
        return 2

    if ok:
        print("\nTruy vấn thử:")
        print(
            '  docker exec documind-postgres psql -U documind -d documind -c '
            '"SELECT page_no, heading_path, left(content,60) FROM source_chunks LIMIT 5"'
        )
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
