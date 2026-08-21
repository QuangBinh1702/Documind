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

## 7. Khi nào được commit

Đây là phần hay bị bỏ qua nhất, và cũng là phần quyết định lịch sử git có đọc
được hay không. Quy ước về *cách viết message* ở trên không cứu được một lịch
sử bị chia sai chỗ.

### Nguyên tắc: một commit = một thay đổi logic trọn vẹn

Hướng dẫn gửi bản vá của nhân Linux — nơi quy tắc này được áp dụng nghiêm ngặt
nhất — nói đúng ba điều, và ba điều đó là đủ:

1. **Tách mỗi thay đổi logic thành một bản vá riêng.** Sửa lỗi và cải thiện
   hiệu năng cho cùng một phân hệ vẫn là **hai** bản vá.
2. **Gom thay đổi liên quan lại với nhau.** Một thay đổi chạm mười tệp nhưng
   phục vụ đúng một mục đích thì là **một** bản vá, không phải mười.
3. **Sau mỗi bản vá, hệ thống phải dựng và chạy được.** Người khác dùng
   `git bisect` sẽ dừng ở bất kỳ điểm nào trong chuỗi.

Điều thứ ba là ràng buộc mạnh nhất: nó loại bỏ hoàn toàn khái niệm "commit dở
dang". Nếu test đang đỏ, hoặc tính năng mới làm được một nửa, thì **chưa tới
lúc commit** — kể cả khi đã viết được nhiều mã.

### Hai chiều sai, đều đã xảy ra trong repo này

| Chiều sai | Ví dụ thật | Vì sao sai |
|---|---|---|
| **Quá nhỏ** | `refactor(extract): import pymupdf under its own name` — đổi một dòng import, commit riêng giữa lúc đang làm việc khác | Nó không hoàn thành việc gì. Nó là một bước tay giữa chừng, đáng lẽ gộp vào commit của phần việc đang làm |
| **Quá to** | `fix: make the pipeline work with real models` — gộp lỗi cấu hình revision, đổi thư viện reranker, hạn mức token của mô hình, nhận diện tiêu đề, và tham số rerank | Năm thay đổi không liên quan gì nhau. Không revert được một phần; `git bisect` chỉ ra commit này thì vẫn chưa biết lỗi nằm ở đâu; và tiêu đề buộc phải mơ hồ vì không có chủ đề chung |

Commit thứ hai đáng lẽ là năm commit, mỗi cái có scope riêng và tự đứng được:
`fix(config)`, `build(rerank)`, `fix(llm)`, `fix(chunker)`, `perf(rerank)`.

### Ba phép thử trước khi commit

1. **Phép thử một câu.** Mô tả được commit trong một câu không có chữ "và"
   không? Không được thì đó là nhiều commit.
2. **Phép thử tự đứng.** Ai đó lấy đúng commit này về, chạy test — xanh không?
   Đọc riêng nó có hiểu được nó làm gì và tại sao không?
3. **Phép thử revert.** Nếu ngày mai phải gỡ bỏ đúng thay đổi này, `git revert`
   một commit có làm được không, hay sẽ kéo theo thứ khác?

### Trong lúc làm thì sao

Cứ làm liên tục, đừng dừng lại để commit từng bước. Khi một đơn vị công việc đã
trọn vẹn thì mới gom lại và commit — dùng `git add -p` để tách nếu trong cây
làm việc đang lẫn nhiều thay đổi khác nhau.

Mã, test và tài liệu của **cùng một thay đổi** đi chung một commit. Một hành vi
mới cùng bằng chứng cho hành vi đó là **một** việc, không phải hai.

### Với đồ án này

Đơn vị tự nhiên là **một user story**, hoặc **một lỗi**, hoặc **một quyết định
kỹ thuật kèm tài liệu của nó**. Footer `Refs: US-xxx` vừa là công cụ truy vết
vừa là phép thử: nếu một commit phải ghi bốn mã story không liên quan thì nó
đang làm quá nhiều việc.

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

Phạm vi — kiểm trước, vì sai ở đây thì message viết hay đến mấy cũng không cứu:

- [ ] Một đơn vị công việc đã **hoàn chỉnh**, không phải một bước giữa chừng
- [ ] Mô tả được trong một câu không có chữ "và"
- [ ] Toàn bộ test xanh **tại chính commit này** (DoD D6 ở `SPEC.md` §A.4)
- [ ] `git revert` một mình commit này gỡ đúng thay đổi, không kéo theo thứ khác
- [ ] Test và tài liệu của cùng thay đổi này nằm chung trong commit

Message:

- [ ] Dòng tiêu đề ở thức mệnh lệnh, dưới 50 ký tự, không dấu chấm cuối
- [ ] Type và scope đúng theo §3 và §4
- [ ] Thân bài giải thích **tại sao**, gói dòng ở 72 ký tự
- [ ] Footer có `Refs:` trỏ về user story

---

## Nguồn

- [Conventional Commits 1.0.0](https://www.conventionalcommits.org/en/v1.0.0/) — cấu trúc dòng tiêu đề
- [How to Write a Git Commit Message — Chris Beams](https://cbea.ms/git-commit/) — cách viết
- [Submitting patches — tài liệu nhân Linux](https://www.kernel.org/doc/html/latest/process/submitting-patches.html) — §"Separate your changes", nguồn của §7
- [Atomic Commits Explained — PHP Architect](https://www.phparch.com/2025/06/atomic-commits-explained-stop-writing-useless-git-messages/)
- [Granularity of (Git) Commits — Kenny Ballou](https://kennyballou.com/blog/2021/03/commit-granularity/) — hai trường phái và đánh đổi
