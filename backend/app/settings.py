"""Cấu hình hệ thống — nguồn duy nhất cho mọi tham số.

Quy tắc D7 của Definition of Done (SPEC.md §A.4): không hardcode ngưỡng, giới
hạn, tên mô hình hay top-k ở bất kỳ nơi nào khác. Nếu một con số ảnh hưởng đến
hành vi, nó phải xuất hiện ở đây và trong `.env.example`.

Các cờ nhóm "Retrieval" là trục của ablation US-046 — đổi chúng phải thay đổi
được hành vi mà không sửa một dòng code nào.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Device = Literal["cpu", "cuda"]
Mode = Literal["privacy", "fast"]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Ứng dụng ────────────────────────────────────────
    app_env: str = "dev"
    log_level: str = "INFO"
    secret_key: str = "doi-gia-tri-nay-truoc-khi-trien-khai"

    access_token_minutes: int = 60
    refresh_token_days: int = 7
    login_max_attempts: int = 5
    login_lockout_minutes: int = 15

    # ── Thiết bị tính toán (SPEC-v1.md §10.0) ───────────
    device: Device = "cpu"
    embedding_device: Device | None = None
    rerank_device: Device | None = None
    ocr_device: Device | None = None
    perf_assertions_enabled: bool = False

    # ── Hạ tầng ─────────────────────────────────────────
    database_url: str = "postgresql+psycopg://documind:documind@localhost:5432/documind"
    redis_url: str = "redis://localhost:6379/0"
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "documind"
    minio_secure: bool = False

    # ── Giới hạn nạp tài liệu (US-006) ──────────────────
    max_file_mb: int = 50
    max_image_mb: int = 10
    max_sources_per_notebook: int = 50
    allowed_extensions: str = "pdf,docx,txt,md,png,jpg,jpeg,webp"

    # ── Chunking (US-008) ───────────────────────────────
    chunk_tokens: int = Field(default=768, ge=256, le=2048)
    chunk_overlap_ratio: float = Field(default=0.15, ge=0.0, le=0.5)
    chunk_respect_headings: bool = True

    # ── Phát hiện scan & OCR (US-023, US-024, US-056) ───
    scan_chars_per_page_threshold: int = 100
    scan_page_ratio_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    text_quality_min: float = Field(default=0.60, ge=0.0, le=1.0)
    ocr_engine: str = "paddle"
    ocr_dpi: int = 300

    # ── Mô hình ─────────────────────────────────────────
    # `fake` dùng adapter băm tất định: chạy được trên laptop không GPU, nhưng
    # chỉ nắm trùng lặp từ vựng chứ không nắm ngữ nghĩa. Mặc định là mô hình
    # thật để không ai vô tình đưa số đo của bản giả vào báo cáo.
    embedding_provider: Literal["bge-m3", "fake"] = "bge-m3"
    embedding_model: str = "BAAI/bge-m3"
    embedding_revision: str | None = None
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_revision: str | None = None
    local_llm_model: str = "qwen3-8b-q4"
    llm_backend: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-flash"

    # ── Retrieval — trục của ablation US-046 ────────────
    retrieval_vector_enabled: bool = True
    retrieval_bm25_enabled: bool = True
    retrieval_top_n_per_branch: int = 50
    rrf_k: int = 60
    rerank_enabled: bool = True
    rerank_top_k: int = 8

    # Ngưỡng "đủ căn cứ" — trên thang ĐÃ sigmoid (US-011 AC-1, US-031 AC-1).
    tau: float = Field(default=0.35, ge=0.0, le=1.0)

    contextual_retrieval_enabled: bool = False
    verifier_enabled: bool = False
    verifier_max_retry: int = 1
    hnsw_ef_search: int = 120

    # ── Định tuyến ý định (US-066) ──────────────────────
    intent_routing_enabled: bool = False
    intent_use_llm_fallback: bool = True

    # ── Bảo mật ngữ cảnh (US-061) ───────────────────────
    context_delimiter: str = "«|CHUNK|»"

    # ── Hội thoại ───────────────────────────────────────
    condense_history_turns: int = 4
    log_condensed_query: bool = False
    default_mode: Mode = "privacy"

    # ── Cache câu trả lời ngoài (US-034, US-035) ────────
    external_cache_similarity: float = Field(default=0.93, ge=0.0, le=1.0)
    external_cache_ttl_days: int = 30
    external_calls_per_day: int = 50

    # ── Suy dẫn ─────────────────────────────────────────

    @field_validator("embedding_device", "rerank_device", "ocr_device", mode="before")
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        """Chuỗi rỗng trong .env nghĩa là "kế thừa DEVICE", không phải giá trị sai."""
        return None if v == "" else v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def embed_device(self) -> Device:
        return self.embedding_device or self.device

    @computed_field  # type: ignore[prop-decorator]
    @property
    def rr_device(self) -> Device:
        return self.rerank_device or self.device

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ocr_dev(self) -> Device:
        return self.ocr_device or self.device

    @computed_field  # type: ignore[prop-decorator]
    @property
    def allowed_extension_set(self) -> frozenset[str]:
        return frozenset(e.strip().lower() for e in self.allowed_extensions.split(",") if e.strip())

    @computed_field  # type: ignore[prop-decorator]
    @property
    def chunk_overlap_tokens(self) -> int:
        return int(self.chunk_tokens * self.chunk_overlap_ratio)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_production(self) -> bool:
        return self.app_env.lower() in {"prod", "production"}

    def warnings(self) -> list[str]:
        """Cảnh báo cấu hình đáng ngờ — hiện khi khởi động, không chặn."""
        out: list[str] = []
        if self.is_production and self.secret_key.startswith("doi-gia-tri-nay"):
            out.append("SECRET_KEY vẫn là giá trị mẫu — phải đổi trước khi triển khai.")
        if self.default_mode == "fast" and not self.gemini_api_key:
            out.append("DEFAULT_MODE=fast nhưng chưa có GEMINI_API_KEY.")
        if self.device == "cuda" and not self.perf_assertions_enabled:
            out.append(
                "DEVICE=cuda nhưng PERF_ASSERTIONS_ENABLED=false — "
                "nếu đây là máy đích, hãy bật để các mốc hiệu năng được kiểm tra."
            )
        if self.device == "cpu" and self.perf_assertions_enabled:
            out.append(
                "DEVICE=cpu nhưng PERF_ASSERTIONS_ENABLED=true — "
                "các mốc hiệu năng sẽ đỏ mà không mang ý nghĩa (US-057 AC-8)."
            )
        if self.embedding_provider == "fake":
            out.append(
                "EMBEDDING_PROVIDER=fake — vector sinh bằng băm, chỉ nắm trùng lặp "
                "từ vựng. Dùng được để phát triển và test logic, KHÔNG dùng được "
                "cho bất kỳ số liệu nào trong báo cáo."
            )
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
