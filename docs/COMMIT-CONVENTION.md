# Quy ước commit

Commit message viết bằng **tiếng Anh**, theo **Conventional Commits 1.0.0** cho
dòng tiêu đề và **bảy quy tắc của Chris Beams** cho phần thân.

Hai chuẩn này bổ sung cho nhau: Conventional Commits quy định *cấu trúc* dòng
tiêu đề để máy đọc được; bảy quy tắc quy định *cách viết* để người đọc được.

---

## 1. Khuôn dạng

```
<type>(<scope>): <description>

<body>

<footer>
```

Ví dụ thật từ repo này:

```
feat(chunker): preserve char offsets when splitting documents

Chunk content is always sliced from full_text using the offsets that were
just computed, never assembled from fragments. This makes INV-1 true by
construction rather than by luck.

Whitespace is stripped by narrowing the span before slicing, not by calling
strip() on the result — stripping afterwards would break the equality that
the whole citation feature depends on.

Refs: US-008, INV-1
```

## 2. Dòng tiêu đề

| Quy tắc | Chi tiết |
|---|---|
| Thức mệnh lệnh | `add`, `fix`, `remove` — **không** `added`, `fixes`, `removing`. Đọc thử: *"If applied, this commit will …"* |
| Chữ thường sau dấu hai chấm | `feat(auth): add refresh token rotation` |
| Không có dấu chấm cuối | |
| Tối đa **50 ký tự**, giới hạn cứng 72 | Dài hơn nghĩa là commit làm quá nhiều việc |
| Không nhắc lại tên tệp | Diff đã nói rồi. Nói **kết quả**, không nói vị trí |

## 3. Type

| Type | Dùng khi | Ví dụ trong đồ án |
|---|---|---|
| `feat` | Thêm năng lực mới cho hệ thống | `feat(retrieval): add reciprocal rank fusion` |
| `fix` | Sửa hành vi sai | `fix(extract): normalize text before splitting paragraphs` |
| `docs` | Chỉ đổi tài liệu | `docs(spec): add two-tier evaluation thresholds` |
| `refactor` | Đổi cấu trúc, **không** đổi hành vi | `refactor(text): extract token counter into a port` |
| `test` | Chỉ thêm hoặc sửa test | `test(chunker): cover NFD input for offset invariant` |
| `build` | Phụ thuộc, Docker, đóng gói | `build(docker): mount model cache as a named volume` |
| `ci` | Quy trình tích hợp | |
| `perf` | Cải thiện hiệu năng | `perf(retrieval): raise hnsw ef_search for small notebooks` |
| `chore` | Việc lặt vặt không thuộc nhóm trên | `chore: ignore generated evaluation results` |
| `revert` | Hoàn tác một commit | |

**Không tự nghĩ ra type mới.** Danh sách trên đã đủ cho mọi thứ trong đồ án.

## 4. Scope

Đặt trong ngoặc đơn, chọn theo **phân hệ**, không theo đường dẫn tệp:

`auth` · `notebook` · `source` · `extract` · `ocr` · `chunker` · `text` ·
`embed` · `retrieval` · `rerank` · `answer` · `citation` · `cache` · `chat` ·
`worker` · `api` · `ui` · `db` · `eval` · `spec` · `docker`

Bỏ scope khi thay đổi trải rộng nhiều phân hệ.

## 5. Thân bài

Cách dòng tiêu đề **một dòng trống**. Gói dòng ở **72 ký tự**.

Giải thích **cái gì** và **tại sao** — *không* giải thích **bằng cách nào**.
Diff đã trả lời "bằng cách nào" rồi; nó không trả lời được "vì sao lại chọn
cách này".

Ba câu hỏi đáng trả lời trong thân bài:

1. Trước khi sửa thì hành vi sai ở đâu?
2. Vì sao chọn cách này mà không chọn cách hiển nhiên hơn?
3. Có đánh đổi hay hạn chế nào người đọc sau cần biết không?

Bỏ thân bài khi commit thật sự tự nói lên hết — ví dụ `chore: add .gitattributes`.

## 6. Footer

Đồ án này dùng footer để truy vết ngược về đặc tả:

```
Refs: US-008, INV-1
```

Ghi mã user story mà commit thực hiện, và mã bất biến nếu commit chạm vào
INV-1…INV-4. Nhờ vậy `git log --grep="US-015"` cho ra toàn bộ lịch sử của một
story — dùng được khi viết Chương 4 của báo cáo.

Thay đổi phá vỡ tương thích:

```
BREAKING CHANGE: source_chunks.tsv is now built from raw text
```

## 7. Một commit làm một việc

Nếu phải viết "and" trong dòng tiêu đề thì đó là hai commit.

Ngoại lệ hợp lý: mã và test của nó đi cùng nhau — một hành vi mới cùng bằng
chứng cho hành vi đó là **một** việc.

## 8. Cách tạo commit trên máy Windows này

Hai cái bẫy đã gặp thật:

**Không truyền message nhiều dòng trực tiếp qua PowerShell.** Dấu ngoặc kép
trong message làm PowerShell cắt nhỏ tham số, git nhận được một mớ pathspec và
commit thất bại. Ghi message ra tệp rồi:

```powershell
git commit -F path\to\message.txt
```

**Ghi tệp bằng UTF-8 không BOM.** `Set-Content -Encoding utf8` của Windows
PowerShell 5.1 chèn BOM, và BOM đó lọt vào đầu dòng tiêu đề commit. Dùng:

```powershell
[System.IO.File]::WriteAllText($path, $text, (New-Object System.Text.UTF8Encoding($false)))
```

## 9. Trước khi commit

- [ ] Dòng tiêu đề ở thức mệnh lệnh, dưới 50 ký tự, không dấu chấm cuối
- [ ] Type và scope đúng theo §3 và §4
- [ ] Thân bài giải thích **tại sao**, gói dòng ở 72 ký tự
- [ ] Footer có `Refs:` trỏ về user story
- [ ] Commit chỉ làm **một** việc
- [ ] Toàn bộ test xanh (Definition of Done D6 ở `SPEC.md` §A.4)

---

## Nguồn

- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/)
- [How to Write a Git Commit Message — Chris Beams](https://cbea.ms/git-commit/)
