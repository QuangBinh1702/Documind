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
    login_window_minutes: int = 5
    """Cửa sổ đếm số lần sai — US-003 AC-5: 5 lần trong 5 phút thì khoá."""

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
    ocr_enabled: bool = True
    """Tắt thì bản scan bị từ chối kèm lý do rõ ràng thay vì đọc bằng OCR.

    Có cờ này vì OCR đắt — hàng chục giây mỗi trang trên CPU — nên lúc phát
    triển hoặc chạy test thường không muốn nó chạy. Nó cũng là trục để US-048 so
    "có OCR" với "không OCR".
    """

    ocr_engine: Literal["rapid", "paddle"] = "rapid"
    """`rapid` chạy PP-OCRv5 qua ONNX Runtime; `paddle` chạy qua PaddlePaddle.

    Mặc định là `rapid` vì `paddle` **hiện không chạy được**: PaddleOCR 3.x tải
    về mô hình mà PaddlePaddle 3.0.0 từ chối nạp
    (`ValueError: Type of attribute: strides is not right`). Adapter `paddle`
    vẫn giữ lại vì US-048 cần so nhiều engine, và vì lỗi này thuộc về phiên bản
    chứ không thuộc về thiết kế.
    """

    ocr_lang: str = "vi"
    """Ngôn ngữ cho engine `paddle`."""

    image_min_side: int = 1600
    """Phóng ảnh nhỏ lên tới cạnh dài này trước khi OCR — US-026.

    Mô hình nhận dạng cần chữ cao khoảng 32 px. Ảnh chụp màn hình một đoạn chữ
    thường thấp hơn nhiều, và OCR trả về rỗng chứ không báo lỗi gì.
    """

    image_max_side: int = 3200
    """Thu ảnh lớn về cạnh dài này. Ảnh 12 MP không đọc tốt hơn ảnh 4 MP."""

    ocr_dpi: int = 300
    ocr_min_confidence: float = Field(default=0.60, ge=0.0, le=1.0)
    """Dòng dưới ngưỡng này được đánh dấu để người rà (US-027), không bị bỏ."""

    # Nhóm mô hình nhận dạng cho engine `rapid`. **Không để mặc định `ch`**: đo
    # thật cho thấy nó đọc tiếng Việt mất sạch dấu mà vẫn tự báo tin cậy 0.98.
    #
    # `latin` là lựa chọn tốt nhất hiện có, nhưng vẫn thiếu ư/ơ/ă/đ nên "thư"
    # thành "thur" và "đại học" thành "dai hoc". Xem chú thích ở
    # `app/adapters/ocr/rapid.py` — có mô hình tiếng Việt riêng thì đổi ở đây.
    ocr_rec_lang: str = "latin"

    # ── Mô hình ─────────────────────────────────────────
    # `fake` dùng adapter băm tất định: chạy được trên laptop không GPU, nhưng
    # chỉ nắm trùng lặp từ vựng chứ không nắm ngữ nghĩa. Mặc định là mô hình
    # thật để không ai vô tình đưa số đo của bản giả vào báo cáo.
    embedding_provider: Literal["bge-m3", "fake"] = "bge-m3"
    embedding_model: str = "BAAI/bge-m3"
    embedding_revision: str | None = None
    embedding_dim: int = 1024
    embedding_batch_size: int = 16
    rerank_provider: Literal["bge", "fake"] = "bge"
    rerank_model: str = "BAAI/bge-reranker-v2-m3"
    rerank_revision: str | None = None
    # `fake` ghép câu trả lời từ ngữ cảnh thay vì sinh ngôn ngữ — dùng để test
    # đường xử lý mà không cần khoá API, quota hay mạng.
    llm_provider: Literal["real", "fake"] = "real"

    # Fast Mode nghĩa là **dữ liệu rời khỏi máy**, không phải "dùng Gemini".
    # Cờ này chọn nhà cung cấp phía sau mà không đổi ngữ nghĩa đó, nên nhãn
    # cảnh báo quyền riêng tư vẫn đúng ở cả hai lựa chọn.
    fast_backend: Literal["gemini", "ollama-cloud"] = "gemini"

    local_llm_model: str = "qwen3-8b-q4"
    # Máy chủ tương thích OpenAI chạy cục bộ: Ollama, vLLM hay llama.cpp.
    # Runtime cụ thể chốt ở spike S2 và không ảnh hưởng tới mã nguồn.
    local_llm_base_url: str = "http://localhost:11434/v1"
    # ── Ollama Cloud ────────────────────────────────────
    # Trọng số mở nhưng chạy trên máy của Ollama, nên **dữ liệu vẫn rời khỏi
    # máy** — đây là một lựa chọn của Fast Mode, không phải của Privacy Mode.
    #
    # `gemma4:31b` lượng tử q4 cần ~18–20 GB VRAM. Máy đích 16 GB còn phải giữ
    # bge-m3 và bge-reranker, nên mô hình này KHÔNG chạy được cục bộ ở đó. Số
    # đo bằng nó thuộc về cột "cloud" của bảng so sánh, không thay được số đo
    # Privacy Mode.
    ollama_cloud_base_url: str = "https://ollama.com/v1"
    ollama_cloud_model: str = "gemma4:31b"
    ollama_cloud_api_key: str | None = None

    gemini_api_key: str | None = None
    # Ghim một phiên bản cụ thể, không dùng bí danh `-latest`. Bí danh trỏ vào
    # mô hình đông người dùng nhất nên hay trả 503, và tệ hơn: nó âm thầm đổi
    # mô hình bên dưới, làm số đo của hai lần chạy đánh giá không so được với
    # nhau (US-045 AC-5 yêu cầu tái lập được).
    #
    # Chọn bản `flash-lite` vì hạn mức miễn phí. Đo thật ngày 21/08/2026:
    # `gemini-3.5-flash` chỉ cho **20 lượt gọi mỗi NGÀY** ở bản miễn phí — đủ
    # để thử vài câu, không đủ để chạy một lượt đánh giá 100 câu. Bản lite chạy
    # 25 lượt liên tiếp không bị chặn. Đây là ràng buộc chi phối, không phải
    # chuyện chất lượng mô hình.
    gemini_model: str = "gemini-3.1-flash-lite"

    # Các mô hình Gemini đời mới "suy nghĩ" trước khi trả lời, và phần suy nghĩ
    # ăn vào CÙNG hạn mức `LLM_MAX_TOKENS`. Đo thật: một câu hỏi nhỏ tốn 361
    # token suy nghĩ cho 39 token trả lời. Với prompt RAG mang 8 đoạn tài liệu,
    # phần suy nghĩ ăn hết hạn mức và câu trả lời trả về RỖNG mà không báo lỗi.
    #
    # Đặt 0 để tắt. Câu trả lời ở đây phải rút ra từ các đoạn đã cho chứ không
    # phải suy luận ra, nên đây gần như không mất gì mà lấy lại được cả hạn mức
    # lẫn phần lớn độ trễ. Đặt số dương để cấp riêng hạn mức cho suy nghĩ.
    gemini_thinking_budget: int = Field(default=0, ge=0)

    llm_temperature: float = 0.0
    llm_max_tokens: int = 1024

    # ── Retrieval — trục của ablation US-046 ────────────
    retrieval_vector_enabled: bool = True
    retrieval_bm25_enabled: bool = True
    retrieval_top_n_per_branch: int = 50
    rrf_k: int = 60
    rerank_enabled: bool = True

    # Bao nhiêu ứng viên đi qua cross-encoder. Đây là hai con số KHÁC nhau và
    # rất dễ nhầm thành một:
    #
    #   rerank_candidates — chấm bao nhiêu  (chi phí)
    #   rerank_top_k      — giữ lại bao nhiêu (ngữ cảnh đưa vào mô hình sinh)
    #
    # Cross-encoder chạy tuyến tính theo số ứng viên, nên đây là tham số chi
    # phối độ trễ nhiều nhất trong cả đường truy xuất. Trên GPU 50 là hợp lý;
    # trên CPU nó biến mỗi câu hỏi thành hàng phút, và lúc đó phải hạ xuống
    # 10–20 chứ không phải tắt hẳn rerank.
    rerank_candidates: int = Field(default=50, ge=1, le=200)
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

    @field_validator(
        "embedding_device", "rerank_device", "ocr_device",
        "embedding_revision", "rerank_revision",
        "gemini_api_key", "ollama_cloud_api_key",
        
        mode="before",
    )
    @classmethod
    def _blank_to_none(cls, v: object) -> object:
        """Một dòng bỏ trống trong `.env` nghĩa là "không đặt", không phải một
        giá trị rỗng.

        Với ba trường thiết bị, chuỗi rỗng nghĩa là "kế thừa DEVICE".

        Với hai trường revision thì hậu quả nặng hơn nhiều và rất khó thấy:
        `EMBEDDING_REVISION=` được truyền xuống HuggingFace như một revision
        thật, nên nó không khớp bản đã có trong cache và **bắt buộc phải ra
        mạng** ở mọi lần nạp mô hình. Máy mất mạng thì mô hình đã tải về vẫn
        không dùng được — đúng thứ US-029 AC-3 hứa là làm được.
        """
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
        thieu_khoa = (
            self.fast_backend == "gemini" and not self.gemini_api_key
        ) or (self.fast_backend == "ollama-cloud" and not self.ollama_cloud_api_key)

        if self.default_mode == "fast" and thieu_khoa:
            out.append(
                f"DEFAULT_MODE=fast với FAST_BACKEND={self.fast_backend} "
                f"nhưng chưa có khoá API tương ứng."
            )
        elif self.default_mode == "fast":
            # SPEC-REVIEW.md §A.4: ở Fast Mode, câu hỏi VÀ các đoạn tài liệu
            # được chọn đều rời khỏi máy. Đề tài lấy "tự triển khai, dữ liệu
            # không ra ngoài" làm luận điểm, nên đánh đổi này phải nhìn thấy
            # được ngay trên giao diện chứ không nằm im trong một tệp cấu hình.
            out.append(
                "DEFAULT_MODE=fast — câu hỏi và nội dung các đoạn tài liệu được "
                "chọn sẽ được gửi tới Google. Đổi sang privacy để chạy hoàn toàn "
                "trên máy bạn."
            )
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
        if self.rerank_provider == "fake":
            out.append(
                "RERANK_PROVIDER=fake — chấm điểm bằng độ bao phủ từ khoá, không "
                "hiểu phủ định hay điều kiện. Ngưỡng τ đo bằng nó không có nghĩa."
            )
        if self.llm_provider == "fake":
            out.append(
                "LLM_PROVIDER=fake — mô hình giả KHÔNG sinh ngôn ngữ. Nó ghép sẵn "
                "một câu nói về chính nó kèm số đoạn trích dẫn, để test đường xử lý "
                "marker. Câu trả lời bạn thấy không phải nội dung tài liệu."
            )
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
