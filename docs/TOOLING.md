# Hiện trạng codebase và kho công cụ

Ngày khảo sát: 2026-08-21 · Phạm vi: `D:\DO_AN` + cấu hình Claude Code cấp người dùng

---

## 1. Hiện trạng codebase

**Chưa có một dòng mã ứng dụng nào.** Repo hiện gồm hai lớp:

### 1.1 Lớp đặc tả (do chúng ta viết)

| Tệp | Vai trò | Trạng thái |
|---|---|---|
| `SPEC.md` v2.2 | Đặc tả **hành vi** — 72 user story, AC dạng Given/When/Then, DoR/DoD, mốc M0–M7, sổ rủi ro | Xong |
| `SPEC-v1.md` v1.0 | Đặc tả **kỹ thuật** — kiến trúc, ports, ERD + DDL, truy vấn retrieval, API, SSE, `.env`, ngân sách VRAM | Xong |
| `SPEC-REVIEW.md` | Căn cứ của các quyết định + việc còn lại | Xong |

### 1.2 Lớp harness (cài sẵn, `repository-harness` core v0.1.10)

`AGENTS.md` + `docs/` + `.agents/skills/` + `.harness-core/` + `scripts/bin/harness.exe`.

Đây **không phải** một framework ứng dụng — nó là một bộ quy ước làm việc cho agent. Bốn điểm đáng chú ý:

- **`docs/WORKFLOW.md`** phân loại công việc thành 4 dạng (read-only · bounded change · durable planned change · operate the application) và đặt ra **cổng thẩm quyền**: không được tự suy ra chính sách từ quy ước code, phải dừng lại hỏi khi thẩm quyền thiếu hoặc mơ hồ. Điều này khớp với cách chúng ta đã làm — mọi ngưỡng đều truy về SPEC.
- **`docs/decisions/`** + `templates/decision.md` — đã có sẵn chỗ cho **nhật ký quyết định** mà `SPEC.md` §A.7 yêu cầu. Không cần tạo cấu trúc mới.
- **`docs/plans/active/`** + `templates/exec-plan.md` — chỗ cho kế hoạch nhiều phiên. Mỗi mốc M nên có một tệp ở đây.
- **`docs/patterns/encoding-invariants.md`** — phương pháp 5 bước biến một quy tắc đã được chấp nhận thành **kiểm tra máy móc có chứng minh hai chiều** (positive proof: ca hợp lệ pass; negative proof: ca vi phạm fail đúng lý do).

### 1.3 Ba khoảng trống phải xử lý trước khi code

| # | Khoảng trống | Ảnh hưởng |
|---|---|---|
| 1 | **Chưa `git init`** | DoD mục D13 yêu cầu commit theo story; `docs/evidence/` ghi commit hash. Không có git thì cả hai vô nghĩa |
| 2 | `docs/evidence/` chưa tồn tại | `SPEC.md` §A.6 yêu cầu mỗi story để lại một tệp bằng chứng |
| 3 | `docs/product/` còn là bản mẫu rỗng | Harness nói rõ: khi có đặc tả sản phẩm, hãy **tách thành các tài liệu sống nhỏ** thay vì giữ một đặc tả khổng lồ làm sổ tay vận hành |

---

## 2. 🔴 Phần cứng thật khác hẳn giả định của SPEC

```
GPU:  NVIDIA GeForce MX570 — 2048 MiB (2 GB) VRAM, compute 8.6
      + Intel Iris Xe (tích hợp)
RAM:  15.7 GB
CPU:  Intel Core i5-1240P (12th gen, 12 nhân)
Phần mềm: Python 3.12.3 · Node v22.14.0 · Docker 29.1.3 · driver 596.08
```

`SPEC.md` ghi *"1 máy, GPU 16GB VRAM"* và `SPEC-v1.md` §10 lập ngân sách 15 GB. **Máy này có 2 GB.**

Đối chiếu với ngân sách đã lập:

| Thành phần | Cần | Vừa 2 GB? |
|---|---|---|
| Qwen3-8B lượng tử 4-bit | ~6–7 GB | ❌ Không |
| bge-m3 (fp16) | ~2.3 GB | ❌ Không |
| bge-reranker-v2-m3 (fp16) | ~2.3 GB | ❌ Không |
| PaddleOCR | ~1 GB | ⚠ Vừa, nhưng chỉ khi chạy một mình |

Đây chính là điều **spike S2** được thiết kế để phát hiện — và nó lộ ra trong 10 giây thay vì một ngày. Nhưng nó lộ ra sớm hơn dự kiến, nên phải quyết định trước khi làm bất cứ việc gì khác.

**Các story bị ảnh hưởng trực tiếp:** US-009 (embedding trên GPU) · US-011 AC-2 (rerank < 800 ms) · US-024 AC-2/AC-5 (OCR < 3 s/trang, trần VRAM) · **US-029 Privacy Mode toàn bộ** · US-057 (ngân sách VRAM).

**✅ Đã giải quyết (2026-08-21):** có một máy khác GPU mạnh hơn. Dự án chạy trên **hai cấu hình** — laptop này để phát triển, máy kia để đo hiệu năng và đánh giá. `SPEC-v1.md` §10.0 đã bổ sung quy tắc để hai cấu hình không phân kỳ (`DEVICE=cpu|cuda` trong config, cấm hardcode `cuda`, tách test hiệu năng bằng `@pytest.mark.perf`, kết quả đánh giá chỉ tính khi chạy trên máy đích).

**Còn thiếu:** cấu hình chính xác của máy đích (tên GPU, dung lượng VRAM). Ngân sách ở `SPEC-v1.md` §10.1 đang giả định 16 GB và phải điều chỉnh khi biết số thật.

---

## 3. Kho công cụ hiện có

### 3.1 Đã cài và dùng được ngay

**Plugin:** chỉ có `superpowers@claude-plugins-official` v6.3.0.
**Skill cấp người dùng:** 17 skill trong `~/.claude/skills`.
**Skill cấp dự án:** 4 skill harness trong `.agents/skills/`.
**Skill dựng sẵn:** `/code-review`, `/simplify`, `/security-review`, `/run`, `/init`, `dataviz`, `design`, `artifact-*`, `/loop`, `/schedule`…
**MCP:** `exa` (tìm kiếm web), `playwright` (điều khiển trình duyệt), `Ref` và `context7` (tra tài liệu thư viện — hiện chập chờn).

### 3.2 Không có "Build Web App Plugin"

Không tồn tại plugin nào mang tên đó. Trong marketplace chính thức có **39 plugin** và **15 plugin ngoài**, chưa cài cái nào ngoài superpowers. Cái gần nhất với ý "xây web app" là **`feature-dev`** — *"quy trình phát triển tính năng với agent chuyên biệt cho khám phá codebase, thiết kế kiến trúc và soát chất lượng"*.

---

## 4. Công cụ nào dùng ở mốc nào

### M0 — Spike và tài liệu kiến trúc

| Công cụ | Dùng làm gì |
|---|---|
| `superpowers:brainstorming` | Chốt hướng xử lý sau phát hiện GPU 2 GB — trước khi viết mã |
| `superpowers:writing-plans` | Biến `SPEC.md` mốc M1 thành `docs/plans/active/m1-nen-mong.md` |
| `Ref` / `context7` / `exa` MCP | Tra tài liệu thật của pgvector, PaddleOCR, FastAPI thay vì viết theo trí nhớ |
| `docs/templates/decision.md` | Ghi quyết định runtime LLM và phương án phần cứng |

### M1 — Nền móng · nơi hai bất biến lõi được thiết lập

| Công cụ | Dùng làm gì |
|---|---|
| ⭐ **`.agents/skills/encode-invariant`** | **Khớp chính xác** với 4 bất biến ở `SPEC-v1.md` §1.3. Skill này biến một quy tắc đã chấp nhận thành kiểm tra máy móc kèm **positive proof và negative proof** — đúng thứ INV-1 (offset) và INV-2 (NFC) cần |
| ⭐ `superpowers:test-driven-development` | Viết `test_offset_roundtrip` và `test_nfc_invariant` **trước** khi viết chunker |
| `superpowers:verification-before-completion` | Ánh xạ 1-1 vào DoD §A.4 và bằng chứng §A.6 — bằng chứng trước khẳng định |
| `/init` | Sinh `CLAUDE.md` để mọi phiên sau tự biết quy ước dự án |

### M2 — Lõi RAG và trích dẫn · giai đoạn quyết định

| Công cụ | Dùng làm gì |
|---|---|
| ⭐ `/code-review` | **Đây là lời giải cho rủi ro "không ai review bạn"** ở J.3b. Chạy sau mỗi story lõi, mức `high` cho retrieval/citation |
| `superpowers:systematic-debugging` | Khi retrieval trả sai chunk — chẩn đoán theo phương pháp thay vì đoán |
| `vercel-react-best-practices` | Next.js 15 + React 19 — đúng ngăn xếp đã chốt |
| ⭐ `playwright` MCP hoặc `claude-in-chrome` | **Chứng minh US-015 bằng máy**: bấm chip `[1]` → viewer nhảy đúng trang → highlight hiện đúng chỗ. Ảnh chụp tự động vào `docs/evidence/` |
| `web-design-guidelines` | Soát bố cục 3 cột theo DoD Loại 3 (1920/1366/<1024, trạng thái rỗng/tải/lỗi, bàn phím) |

### M3–M5 — OCR, LLM hai tầng, hoàn thiện

| Công cụ | Dùng làm gì |
|---|---|
| `/security-review` | US-061 prompt injection, US-005 cách ly dữ liệu chéo, xác thực |
| `frontend-design` hoặc `ui-ux-pro-max` | Giao diện 3 cột, chip trích dẫn, trạng thái nạp tài liệu |
| `design` (canvas) | Sơ đồ bố cục giao diện cho Chương 3 — 4 hình mà US-060 yêu cầu |
| `/simplify` | Dọn mã sau mỗi mốc, giữ DoD D4 |

### M6 — Đánh giá định lượng · nơi đồ án ăn điểm

| Công cụ | Dùng làm gì |
|---|---|
| ⭐ **`dataviz`** | **Toàn bộ biểu đồ Chương 5**: cột ablation 6 dòng, đường P/R/F1 theo τ, cột RAGAS, histogram điểm tổng hợp, biểu đồ theo loại câu hỏi. Skill này ép tính nhất quán màu/trục/nhãn giữa các hình — thứ phân biệt báo cáo chỉn chu với báo cáo ghép từ nhiều lần chạy matplotlib |
| `artifact-diagramming` | Sơ đồ giải thích cơ chế cho Chương 3–4 |

### M7 — Báo cáo và bảo vệ

| Công cụ | Dùng làm gì |
|---|---|
| `Artifact` | Trang báo cáo tiến độ chia sẻ được cho thầy hướng dẫn |
| `artifact-design` | Chuẩn bị trước khi xuất bản bất kỳ trang nào |
| `.agents/skills/onboard-repository` | Sinh tài liệu kiến trúc **từ mã thật** ở cuối kỳ, đối chiếu với `SPEC-v1.md` để phát hiện chỗ đã trôi khỏi thiết kế |

---

## 5. Đề xuất cài thêm

| Plugin | Vì sao | Ưu tiên |
|---|---|---|
| **`feature-dev`** | Gần nhất với "Build Web App Plugin" — agent chuyên cho khám phá codebase, thiết kế kiến trúc, soát chất lượng | Cao |
| **`hookify`** | Biến DoD thành **hook tự động**: chặn commit nếu test offset đỏ, cảnh báo khi có `unicodedata.normalize` ngoài `normalize.py`. Làm một mình thì tự động hoá kỷ luật là đáng giá nhất | Cao |
| `context7` (ngoài) | Tra tài liệu thư viện chính xác theo phiên bản — pgvector, PaddleOCR, Celery | Trung bình |
| `pr-review-toolkit` | Agent soát chuyên biệt: test, xử lý lỗi, thiết kế kiểu, chất lượng mã | Trung bình |
| `skill-creator` | Đóng gói quy ước dự án thành một skill `documind` để mọi phiên sau tự tuân theo | Trung bình |

**Chưa nên cài:** `code-modernization` (không có legacy), `mcp-server-dev`, các `*-lsp` (trừ `pyright-lsp` và `typescript-lsp` nếu muốn chẩn đoán kiểu trong phiên).

---

## 6. Trùng lặp cần chọn một

Có **7 skill frontend** chồng nhau: `frontend-design` · `design-taste-frontend` · `ui-ux-pro-max` · `gpt-taste` · `stitch-design-taste` · `redesign-existing-projects` · `imagegen-frontend-web`.

Dùng nhiều cái cùng lúc sẽ cho ra giao diện không nhất quán. **Chọn một làm chuẩn** và ghi vào `docs/decisions/`. Đề xuất:

- **`frontend-design`** — bản chính thức, hợp với ứng dụng công cụ nghiêm túc; hoặc
- **`ui-ux-pro-max`** — nếu muốn hệ thống thiết kế có cấu trúc rõ (bảng màu, cặp font, thành phần) để giữ nhất quán suốt 8 mốc.

`gpt-taste` và `stitch-design-taste` thiên về trang tiếp thị có hiệu ứng cuộn — **không hợp** với ứng dụng ba cột dùng để làm việc. `imagegen-*` chỉ sinh ảnh mockup, không sinh mã.

---

## 7. Ba đòn bẩy lớn nhất

1. **`encode-invariant` + `test-driven-development` cho INV-1 và INV-2.** Rủi ro số một của đồ án là offset lệch. Repo đã sẵn một phương pháp yêu cầu chứng minh hai chiều — ca hợp lệ pass **và** ca vi phạm fail đúng lý do. Dùng nó ở M1, không phải khi đã hỏng.

2. **`/code-review` sau mỗi story lõi.** `SPEC.md` J.3b nêu rủi ro lớn nhất của việc làm một mình là không ai soát chéo. Đây là câu trả lời trực tiếp, và nó miễn phí.

3. **`playwright` để chứng minh US-015 bằng máy.** Story rủi ro cao nhất của đồ án là highlight theo bbox. Kiểm thử tay một lần không chứng minh được nó vẫn đúng sau mười lần sửa. Một kịch bản Playwright chụp ảnh sau mỗi lần bấm chip vừa là hồi quy, vừa là hình cho Chương 4.
