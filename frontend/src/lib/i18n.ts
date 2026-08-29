/**
 * Chuỗi giao diện, hai ngôn ngữ — US-036.
 *
 * Không dùng thư viện i18n nào. Ở quy mô này — hai ngôn ngữ, một bó chuỗi
 * phẳng, không có số nhiều phức tạp kiểu tiếng Nga — một thư viện mang theo
 * nhiều khái niệm hơn là công việc thật sự cần.
 *
 * Bảng tiếng Việt là **nguồn chân lý về danh sách khoá**: kiểu `Khoa` suy ra từ
 * chính nó, nên thêm một chuỗi mà quên dịch sẽ đỏ ở `tsc` chứ không lặng lẽ
 * trôi ra giao diện (AC-3). Bảng tiếng Anh khai là `Partial`, và chỗ nào thiếu
 * thì rơi về tiếng Việt — bản dịch chưa xong vẫn phải đọc được, không được hiện
 * ra khoá thô kiểu `nav.sources.title` (AC-4).
 *
 * Tham số chèn theo tên: `t("nguon.datXong", { ten: "Quy chế" })`. Ghép chuỗi
 * bằng `+` ở chỗ gọi sẽ khoá cứng trật tự từ của tiếng Việt vào mã.
 */

export type NgonNgu = "vi" | "en";

export const VI = {
  // ── Chung ──────────────────────────────────────────
  "chung.dangTai": "Đang tải…",
  "chung.thuLai": "Thử lại",
  "chung.huy": "Huỷ",
  "chung.xoa": "Xoá",
  "chung.dong": "Đóng",
  "chung.soTrang": "{so} trang",
  "chung.soTrangNhieu": "{so} trang",
  "chung.dangXuLy": "đang xử lý",
  "chung.matKetNoi":
    "Mất kết nối tới máy chủ. Đang tự thử lại — công việc của bạn không bị mất.",

  // ── Xác thực ───────────────────────────────────────
  "auth.dangNhap": "Đăng nhập",
  "auth.dangKy": "Tạo tài khoản",
  "auth.dangXuat": "Đăng xuất",
  "auth.email": "Email",
  "auth.matKhau": "Mật khẩu",
  "auth.phienHetHan": "Phiên đăng nhập đã hết hạn.",
  "auth.gioiThieu":
    "Hỏi đáp trên tài liệu của bạn, luôn kèm trích dẫn kiểm chứng được.",
  "auth.dangKiemTra": "Đang kiểm tra phiên đăng nhập…",
  "auth.emailSai": "Email không đúng định dạng.",
  "auth.matKhauNgan": "Mật khẩu phải có ít nhất {so} ký tự.",
  "auth.matKhauGoiY": "ít nhất 8 ký tự",
  "auth.dangXuLy": "Đang xử lý…",
  "auth.khongKetNoi": "Không kết nối được máy chủ.",
  "auth.daCoTaiKhoan": "Đã có tài khoản? Đăng nhập",
  "auth.chuaCoTaiKhoan": "Chưa có tài khoản? Đăng ký",
  "auth.slogan": "Hỏi tài liệu của bạn. Mỗi câu trả lời chỉ ra đúng chỗ nó lấy từ đâu.",
  "auth.sloganMoTa":
    "Tải quy chế, giáo trình, bản scan hay ảnh chụp lên. Hệ thống tìm trong đó và trả lời kèm số trích dẫn — bấm vào là mở đúng trang, đúng đoạn. Không đủ căn cứ thì nói thẳng là không biết.",
  "auth.viDuTraLoi": "Học bổng loại giỏi bằng 120% mức học phí ",
  "auth.viDuTraLoi2": ", xét trong 30 ngày sau khi kết thúc học kỳ ",
  "auth.chanTrang": "Đồ án tốt nghiệp · chạy hoàn toàn trên máy của bạn nếu muốn",

  // ── Notebook ───────────────────────────────────────
  "nb.cuaBan": "Notebook của bạn",
  "nb.veDanhSach": "Về danh sách notebook",
  "nb.tenMoi": "Tên notebook mới — ví dụ: Quy chế đào tạo",
  "nb.tao": "Tạo",
  "nb.chuaCo": "Chưa có notebook nào",
  "nb.chuaCoMoTa":
    "Tạo một notebook cho mỗi môn học hoặc mỗi bộ tài liệu, rồi tải tệp vào đó. Hỏi trong notebook nào thì chỉ tìm trong tài liệu của notebook đó.",
  "nb.khongTaiDuoc": "Không tải được danh sách notebook.",
  "nb.khongTaoDuoc": "Không tạo được notebook.",
  "nb.khongTimThay": "Không tìm thấy notebook này.",
  "nb.chuaCoTaiLieu": "chưa có tài liệu",
  "nb.soTaiLieu": "{so} tài liệu",
  "nb.daXuLy": "{xong}/{tong} tài liệu đã xử lý",
  "nb.doiTen": "Bấm để đổi tên",
  "nb.soLieu": "Số liệu",
  "nb.capNhat": "Cập nhật {luc}",
  "tg.vuaXong": "vừa xong",
  "tg.phutTruoc": "{so} phút trước",
  "tg.gioTruoc": "{so} giờ trước",
  "tg.ngayTruoc": "{so} ngày trước",

  // ── Nguồn ──────────────────────────────────────────
  "nguon.tieuDe": "Nguồn",
  "nguon.keoTha": "Kéo thả tệp vào đây",
  "nguon.dinhDang": "PDF · DOCX · TXT · MD · ảnh",
  "nguon.chonTep": "Chọn tệp",
  "nguon.chuaCo": "Chưa có tài liệu nào. Tải một tệp lên để bắt đầu hỏi.",
  "nguon.khongTaiDuoc": "Không tải được {ten}.",
  "nguon.hoiTrong": "Hỏi trong tài liệu này",
  "nguon.xoaHoi": 'Xoá "{ten}"?',
  "nguon.datXong": "{ten} đã xử lý xong — hỏi được rồi.",

  "trangThai.queued": "đang chờ",
  "trangThai.parsing": "đang đọc",
  "trangThai.ocr": "đang nhận dạng chữ",
  "trangThai.chunking": "đang chia đoạn",
  "trangThai.embedding": "đang lập chỉ mục",
  "trangThai.ready": "sẵn sàng",
  "trangThai.failed": "lỗi",

  // ── Hội thoại ──────────────────────────────────────
  "chat.hoi": "Hỏi",
  "chat.oNhap": "Hỏi gì đó về tài liệu…",
  "chat.chuaSanSang": "Chưa có tài liệu sẵn sàng",
  "chat.batDau": "Hỏi gì đó về tài liệu của bạn",
  "chat.batDauMoTa":
    "Mỗi khẳng định trong câu trả lời sẽ kèm số đoạn. Bấm vào số đó để đọc đúng đoạn văn gốc.",
  "chat.chuaCoTaiLieu": "Chưa có tài liệu nào sẵn sàng",
  "chat.canXuLyXong": "Tài liệu cần được xử lý xong trước khi hỏi.",
  "chat.taiLenDauTien": "Tải tài liệu đầu tiên lên",
  "chat.ban": "Bạn:",
  "chat.soTrichDan": "{so} trích dẫn — bấm số để xem đoạn gốc",
  "chat.luuLai": "Lưu lại cuộc hỏi đáp này",
  "chat.khongXuatDuoc": "Không xuất được tệp. Thử lại sau.",
  "chat.hoiThoaiMoi": "Hội thoại mới",
  "chat.hoiNgoai": "Hỏi bằng kiến thức ngoài tài liệu",
  "chat.nhanNgoai": "Ngoài tài liệu — không có trích dẫn",
  "chat.xacNhanNgoai":
    "Câu hỏi này sẽ được gửi tới một dịch vụ bên ngoài. Tài liệu của bạn KHÔNG được gửi kèm.",
  "chat.dongYGui": "Đồng ý gửi",
  "chat.tuCache": "Lấy lại từ câu đã hỏi trước: “{cau}”",
  "chat.chep": "Chép câu trả lời",
  "chat.daChep": "Đã chép",
  "chat.chonPhien": "Chọn hội thoại",
  "chat.phienMoi": "Hội thoại mới…",
  "chat.phienKhongTen": "(không tên)",
  "chat.goiYPhim": "Enter để gửi · Shift+Enter xuống dòng",
  "chat.goiYPhimThem": " · ↑ lấy lại câu đã hỏi · Ctrl+V dán ảnh để hỏi trên ảnh đó",
  "chat.dung": "Dừng",
  "chat.daDung": "đã dừng giữa chừng",
  "chat.daDungTruocKhiTraLoi": "Đã dừng trước khi có câu trả lời.",
  "chat.khongCoTrongTaiLieu":
    "Tài liệu của bạn không có thông tin này — dưới đây là câu trả lời từ mô hình ngoài.",
  "chat.tuDongNgoai": "Tự động hỏi ra ngoài",
  "chat.tuDongNgoaiMoTa":
    "Khi tài liệu không có câu trả lời, hỏi thẳng dịch vụ bên ngoài mà không phải bấm thêm. Chỉ áp dụng cho lần mở trang này; tắt lại khi bạn tải lại trang.",
  "chat.boDinhKem": "Bỏ ảnh này",
  "chat.dangTaiAnh": "Đang tải {ten} lên…",
  "chat.dangXuLyAnh": "Đang đọc chữ trong ảnh — hỏi được ngay khi xong…",
  "chat.anhKhongTaiDuoc": "Không tải được ảnh lên. Thử lại.",
  "chat.anhHong": "Không đọc được ảnh này. Xem lý do ở cột nguồn.",
  "chat.anhLau": "Ảnh chưa xử lý xong. Đợi thêm một chút rồi hỏi lại.",

  "buoc.reading": "đang đọc tài liệu",
  "buoc.retrieving": "đang tìm trong tài liệu",
  "buoc.reranking": "đang xếp hạng đoạn liên quan",
  "buoc.generating": "đang viết câu trả lời",
  "buoc.verifying": "đang kiểm định",
  "buoc.regenerating": "đang viết lại",
  "buoc.calling_external": "đang hỏi dịch vụ bên ngoài",

  // ── Cột tài liệu ───────────────────────────────────
  "xem.doanTrichDan": "Đoạn được trích dẫn",
  "xem.veDoanTrich": "Về đoạn trích",
  "xem.chuaChon": "Chưa chọn trích dẫn nào",
  "xem.khongRoTrang": "Không rõ trang",
  "xem.trangSo": "Trang {so}",
  "xem.trangTruoc": "Trang trước",
  "xem.trangSau": "Trang sau",
  "xem.chuTuAnh": "Chữ đọc được từ ảnh",
  "xem.dangDungTrang": "đang dựng trang…",
  "xem.mucPhong": "Mức phóng",
  "xem.vuaBeNgang": "Vừa bề ngang",
  "xem.khongMoDuoc": "Không mở được tệp gốc của tài liệu này.",
  "xem.khongDocDuocPdf": "Tệp PDF này không đọc được.",
  "xem.khongMoDuocDungDoan":
    "Không mở được tệp gốc, nên đây là nguyên văn đoạn được trích thay vì trang tài liệu.",
  "xem.khongTaiDuocTrichDan":
    "Không tải được đoạn trích dẫn. Nguồn có thể đã bị xoá.",

  // ── Chia sẻ ────────────────────────────────────────
  "chiaSe.nut": "Chia sẻ",
  "chiaSe.tieuDe": "Chia sẻ đoạn hội thoại này",
  "chiaSe.chuaCoHoiThoai":
    "Hãy hỏi một câu trước đã. Liên kết chia sẻ mang theo đúng đoạn hội thoại đang mở, nên phải có gì đó để gửi đi.",
  "chiaSe.chuaCoMoTa":
    "Tạo một liên kết để người khác đọc đúng đoạn hội thoại này cùng các tài liệu nguồn của nó. Những hội thoại khác trong notebook vẫn riêng tư, và bạn thu hồi được bất cứ lúc nào.",
  "chiaSe.daCoMoTa":
    "Ai có liên kết này đều đọc được đoạn hội thoại và mở được tài liệu nguồn, kể cả khi chưa đăng nhập. Họ không sửa hay xoá được gì.",
  "chiaSe.tao": "Tạo liên kết",
  "chiaSe.chep": "Chép liên kết",
  "chiaSe.daChep": "Đã chép",
  "chiaSe.thuHoi": "Thu hồi",
  "chiaSe.muonHoiPhaiDangNhap":
    "Muốn hỏi thêm thì người xem phải đăng nhập, và câu hỏi của họ vào lịch sử của chính họ.",
  "chiaSe.chiDoc": "chỉ đọc",
  "chiaSe.hetHieuLuc": "Liên kết này không tồn tại hoặc đã bị thu hồi.",
  "chiaSe.xinLienKetMoi": "Hỏi người đã gửi liên kết để nhận một liên kết mới.",
  "chiaSe.dangNhapDeHoi": "Đăng nhập để hỏi tiếp",
  "chiaSe.dangNhapMoTa":
    "Bạn đang đọc một đoạn hội thoại được chia sẻ. Đăng nhập để hỏi thêm về chính những tài liệu này — câu hỏi của bạn sẽ nằm trong lịch sử của bạn.",
  "chiaSe.hoiThemCuaToi": "Bạn đã hỏi thêm",
  "chiaSe.hoiThoaiGoc": "Đoạn hội thoại được chia sẻ",

  // ── Thống kê ───────────────────────────────────────
  "tk.tieuDe": "Số liệu hệ thống",
  "tk.khoTriThuc": "Kho tri thức",
  "tk.notebook": "Notebook",
  "tk.taiLieu": "Tài liệu",
  "tk.doanTriThuc": "Đoạn tri thức",
  "tk.dungLuong": "Dung lượng",
  "tk.loaiCauTraLoi": "Loại câu trả lời",
  "tk.doTre": "Độ trễ theo chế độ",
  "tk.trenMay": "Xử lý trên máy",
  "tk.guiRaNgoai": "Có gửi ra ngoài",
  "tk.trungBinh": "Trung bình",
  "tk.soLuot": "Số lượt",
  "tk.goiNgoai": "Gọi ra ngoài và bộ nhớ đệm",
  "tk.luotGoiThat": "Lượt gọi thật",
  "tk.luotTuDem": "Lượt lấy từ đệm",
  "tk.tiLeDungLai": "Tỉ lệ dùng lại",
  "tk.cauDangLuu": "Câu đang lưu",
  "tk.luotHoi30Ngay": "Lượt hỏi 30 ngày gần nhất",
  "tk.chuaCoLuotNao": "Chưa có lượt nào ở chế độ này.",
  "tk.chuaCoCauTraLoi": "Chưa có câu trả lời nào. Hỏi vài câu rồi quay lại đây.",
  "tk.chuaCoLuotHoi": "Chưa có lượt hỏi nào trong 30 ngày qua.",
  "tk.khongTaiDuoc": "Không tải được số liệu.",

  "kind.grounded": "Có căn cứ trong tài liệu",
  "kind.no_answer": "Từ chối vì không đủ căn cứ",
  "kind.external": "Hỏi ra ngoài tài liệu",
  "kind.cached_external": "Lấy lại từ bộ nhớ đệm",
  "kind.chitchat": "Trò chuyện",

  // ── Bố cục và nhãn phụ ─────────────────────────────
  "cot.nguon": "Nguồn",
  "cot.hoiThoai": "Hội thoại",
  "cot.taiLieu": "Tài liệu",
  "cot.keoCotNguon": "Đổi độ rộng cột nguồn",
  "cot.keoCotTaiLieu": "Đổi độ rộng cột tài liệu",
  "chip.xemDoanGoc": "Xem đoạn gốc",
  "chip.khongTonTai": "Trích dẫn không tồn tại",
  "chip.nguonDaXoa": "Nguồn của trích dẫn này đã bị xoá",
  "loi.khongLuuDuoc": "Không lưu được thay đổi. Thử lại.",
  "loi.trangHong": "Có lỗi khi hiển thị trang này.",
  "loi.khongTimThayTrang": "Không có trang nào ở địa chỉ này.",
  "loi.veTrangChu": "Về trang chủ",
  "nb.xoaHoi": 'Xoá notebook "{ten}" cùng toàn bộ tài liệu và hội thoại trong đó?',
  "nb.xoa": "Xoá notebook",
  "tk.doiMatKhau": "Đổi mật khẩu",
  "tk.matKhauCu": "Mật khẩu hiện tại",
  "tk.matKhauMoi": "Mật khẩu mới",
  "tk.daDoiMatKhau": "Đã đổi mật khẩu. Các phiên đăng nhập khác đã bị đăng xuất.",
  "tk.luu": "Lưu",
  "xem.huongDanChip":
    "Mỗi khẳng định trong câu trả lời kèm một số. Bấm vào số đó để đọc đúng đoạn văn mà câu trả lời dựa vào.",
  "rt.ngoai": "Xử lý bên ngoài",
  "rt.ngoaiMoTa":
    "Câu hỏi và những đoạn tài liệu liên quan được gửi tới một dịch vụ xử lý bên ngoài. Muốn mọi thứ ở lại máy này thì chuyển sang chế độ xử lý cục bộ.",
  "rt.cucBo": "Xử lý trên máy này",
  "rt.cucBoMoTa":
    "Toàn bộ xử lý diễn ra trên máy này. Không có nội dung nào được gửi đi đâu cả.",
  "tk.moTaLoaiCauTraLoi":
    "Tỉ lệ câu trả lời dựa trên tài liệu là thước đo trực tiếp của việc hệ thống có làm đúng việc nó hứa hay không.",
  "tk.moTaDoTre":
    "Đo trên máy đang chạy. Con số của máy phát triển không thay được con số của máy đích.",
  "tk.bieuDoNhan": "Số lượt hỏi theo ngày",
  "tk.luotNgay": "{ngay}: {so} lượt",

  // ── Cài đặt ────────────────────────────────────────
  "caiDat.tieuDe": "Cài đặt",
  "caiDat.taiKhoan": "Tài khoản",
  "chung.toiNoiDung": "Tới nội dung chính",
  "nb.tuyChon": "Tuỳ chọn notebook",
  "chat.xuat": "Xuất",

  // ── Giao diện ──────────────────────────────────────
  "gd.cheDoHienThi": "Chế độ hiển thị",
  "gd.sang": "Sáng",
  "gd.toi": "Tối",
  "gd.theoMay": "Tự động",
  "gd.ngonNgu": "Ngôn ngữ",
  "gd.tiengViet": "Tiếng Việt",
  "gd.tiengAnh": "Tiếng Anh",
} as const;

export type Khoa = keyof typeof VI;

export const EN: Partial<Record<Khoa, string>> = {
  "chung.dangTai": "Loading…",
  "chung.thuLai": "Try again",
  "chung.huy": "Cancel",
  "chung.xoa": "Delete",
  "chung.dong": "Close",
  // Tiếng Việt không chia số nhiều, tiếng Anh thì có — nên "số trang" phải là
  // MỘT khoá nhận tham số, không phải chuỗi "trang" ghép tay ở chỗ gọi. Ghép
  // tay cho ra "1 pages".
  "chung.soTrang": "{so} page",
  "chung.soTrangNhieu": "{so} pages",
  "chung.dangXuLy": "processing",
  "chung.matKetNoi":
    "Lost connection to the server. Retrying — your work is safe.",

  "auth.dangNhap": "Sign in",
  "auth.dangKy": "Create account",
  "auth.dangXuat": "Sign out",
  "auth.email": "Email",
  "auth.matKhau": "Password",
  "auth.phienHetHan": "Your session has expired.",
  "auth.gioiThieu":
    "Ask questions about your own documents, always with citations you can check.",
  "auth.dangKiemTra": "Checking your session…",
  "auth.emailSai": "That does not look like an email address.",
  "auth.matKhauNgan": "The password needs at least {so} characters.",
  "auth.matKhauGoiY": "at least 8 characters",
  "auth.dangXuLy": "Working…",
  "auth.khongKetNoi": "Could not reach the server.",
  "auth.daCoTaiKhoan": "Already have an account? Sign in",
  "auth.chuaCoTaiKhoan": "No account yet? Create one",
  "auth.slogan": "Ask your documents. Every answer points to exactly where it came from.",
  "auth.sloganMoTa":
    "Upload regulations, textbooks, scans or photos. The system searches them and answers with numbered citations — click one to open the right page and passage. When the evidence is not there, it says so.",
  "auth.viDuTraLoi": "The good-standing scholarship equals 120% of tuition ",
  "auth.viDuTraLoi2": ", reviewed within 30 days of the end of term ",
  "auth.chanTrang": "Graduation project · can run entirely on your own machine",

  "nb.cuaBan": "Your notebooks",
  "nb.veDanhSach": "Back to notebooks",
  "nb.tenMoi": "New notebook name — e.g. Academic regulations",
  "nb.tao": "Create",
  "nb.chuaCo": "No notebooks yet",
  "nb.chuaCoMoTa":
    "Make one notebook per course or per set of documents, then upload files into it. A question searches only the documents in the notebook you ask it from.",
  "nb.khongTaiDuoc": "Could not load your notebooks.",
  "nb.khongTaoDuoc": "Could not create the notebook.",
  "nb.khongTimThay": "This notebook does not exist.",
  "nb.chuaCoTaiLieu": "no documents",
  "nb.soTaiLieu": "{so} documents",
  "nb.daXuLy": "{xong}/{tong} documents processed",
  "nb.doiTen": "Click to rename",
  "nb.soLieu": "Statistics",
  "nb.capNhat": "Updated {luc}",
  "tg.vuaXong": "just now",
  "tg.phutTruoc": "{so} min ago",
  "tg.gioTruoc": "{so} h ago",
  "tg.ngayTruoc": "{so} days ago",

  "nguon.tieuDe": "Sources",
  "nguon.keoTha": "Drop files here",
  "nguon.dinhDang": "PDF · DOCX · TXT · MD · images",
  "nguon.chonTep": "Choose files",
  "nguon.chuaCo": "No documents yet. Upload one to start asking.",
  "nguon.khongTaiDuoc": "Could not upload {ten}.",
  "nguon.hoiTrong": "Search this document",
  "nguon.xoaHoi": 'Delete "{ten}"?',
  "nguon.datXong": "{ten} is ready — you can ask about it now.",

  "trangThai.queued": "queued",
  "trangThai.parsing": "reading",
  "trangThai.ocr": "recognising text",
  "trangThai.chunking": "splitting into passages",
  "trangThai.embedding": "indexing",
  "trangThai.ready": "ready",
  "trangThai.failed": "failed",

  "chat.hoi": "Ask",
  "chat.oNhap": "Ask something about your documents…",
  "chat.chuaSanSang": "No document is ready yet",
  "chat.batDau": "Ask something about your documents",
  "chat.batDauMoTa":
    "Every claim in the answer carries a passage number. Click it to read the original text.",
  "chat.chuaCoTaiLieu": "No document is ready yet",
  "chat.canXuLyXong": "A document has to finish processing before you can ask about it.",
  "chat.taiLenDauTien": "Upload your first document",
  "chat.ban": "You:",
  "chat.soTrichDan": "{so} citations — click a number to see the original passage",
  "chat.luuLai": "Save this conversation",
  "chat.khongXuatDuoc": "Could not export the file. Try again later.",
  "chat.hoiThoaiMoi": "New conversation",
  "chat.hoiNgoai": "Ask using outside knowledge",
  "chat.nhanNgoai": "Outside your documents — no citations",
  "chat.xacNhanNgoai":
    "This question will be sent to an external service. Your documents are NOT included.",
  "chat.dongYGui": "Send it",
  "chat.tuCache": "Reused from an earlier question: “{cau}”",
  "chat.chep": "Copy answer",
  "chat.daChep": "Copied",
  "chat.chonPhien": "Choose a conversation",
  "chat.phienMoi": "New conversation…",
  "chat.phienKhongTen": "(untitled)",
  "chat.goiYPhim": "Enter to send · Shift+Enter for a new line",
  "chat.goiYPhimThem":
    " · ↑ for an earlier question · Ctrl+V to paste an image and ask about it",
  "chat.dung": "Stop",
  "chat.daDung": "stopped part-way",
  "chat.daDungTruocKhiTraLoi": "Stopped before the answer started.",
  "chat.khongCoTrongTaiLieu":
    "Your documents do not hold this — below is an answer from an outside model.",
  "chat.tuDongNgoai": "Auto-ask outside",
  "chat.tuDongNgoaiMoTa":
    "When your documents do not hold the answer, ask the external service straight away instead of waiting for another click. Applies to this page visit only; it turns off when you reload.",
  "chat.boDinhKem": "Remove this image",
  "chat.dangTaiAnh": "Uploading {ten}…",
  "chat.dangXuLyAnh": "Reading the text in the image — ready to ask in a moment…",
  "chat.anhKhongTaiDuoc": "Could not upload the image. Try again.",
  "chat.anhHong": "This image could not be read. See why in the sources column.",
  "chat.anhLau": "The image is still processing. Wait a moment and ask again.",

  "buoc.reading": "reading the documents",
  "buoc.retrieving": "searching your documents",
  "buoc.reranking": "ranking relevant passages",
  "buoc.generating": "writing the answer",
  "buoc.verifying": "verifying",
  "buoc.regenerating": "rewriting",
  "buoc.calling_external": "asking the external service",

  "xem.doanTrichDan": "Cited passage",
  "xem.veDoanTrich": "Back to passage",
  "xem.chuaChon": "No citation selected",
  "xem.khongRoTrang": "Page unknown",
  "xem.trangSo": "Page {so}",
  "xem.trangTruoc": "Previous page",
  "xem.trangSau": "Next page",
  "xem.chuTuAnh": "Text recognised from the image",
  "xem.dangDungTrang": "rendering page…",
  "xem.mucPhong": "Zoom",
  "xem.vuaBeNgang": "Fit width",
  "xem.khongMoDuoc": "Could not open the original file.",
  "xem.khongDocDuocPdf": "This PDF could not be read.",
  "xem.khongMoDuocDungDoan":
    "The original file could not be opened, so this is the cited passage itself rather than the page it came from.",
  "xem.khongTaiDuocTrichDan":
    "Could not load the cited passage. The source may have been deleted.",

  "chiaSe.nut": "Share",
  "chiaSe.tieuDe": "Share this conversation",
  "chiaSe.chuaCoHoiThoai":
    "Ask something first. A share link carries the conversation you have open, so there has to be one to send.",
  "chiaSe.chuaCoMoTa":
    "Create a link so others can read this exact conversation along with the sources behind it. Your other conversations in this notebook stay private, and you can revoke the link at any time.",
  "chiaSe.daCoMoTa":
    "Anyone with this link can read the conversation and open the source documents, even without signing in. They cannot change or delete anything.",
  "chiaSe.tao": "Create link",
  "chiaSe.chep": "Copy link",
  "chiaSe.daChep": "Copied",
  "chiaSe.thuHoi": "Revoke",
  "chiaSe.muonHoiPhaiDangNhap":
    "To ask follow-up questions, viewers must sign in, and their questions go into their own history.",
  "chiaSe.chiDoc": "read-only",
  "chiaSe.hetHieuLuc": "This link does not exist or has been revoked.",
  "chiaSe.xinLienKetMoi": "Ask whoever sent it for a new link.",
  "chiaSe.dangNhapDeHoi": "Sign in to ask",
  "chiaSe.dangNhapMoTa":
    "You are reading a shared conversation. Sign in to ask your own questions about these same documents — they will go into your history.",
  "chiaSe.hoiThemCuaToi": "Your follow-up questions",
  "chiaSe.hoiThoaiGoc": "Shared conversation",

  "tk.tieuDe": "System statistics",
  "tk.khoTriThuc": "Knowledge base",
  "tk.notebook": "Notebooks",
  "tk.taiLieu": "Documents",
  "tk.doanTriThuc": "Passages",
  "tk.dungLuong": "Storage",
  "tk.loaiCauTraLoi": "Answer types",
  "tk.doTre": "Latency by mode",
  "tk.trenMay": "Processed on this machine",
  "tk.guiRaNgoai": "Sent to an external service",
  "tk.trungBinh": "Average",
  "tk.soLuot": "Count",
  "tk.goiNgoai": "External calls and cache",
  "tk.luotGoiThat": "Real calls",
  "tk.luotTuDem": "Served from cache",
  "tk.tiLeDungLai": "Reuse rate",
  "tk.cauDangLuu": "Cached answers",
  "tk.luotHoi30Ngay": "Questions in the last 30 days",
  "tk.chuaCoLuotNao": "No questions in this mode yet.",
  "tk.chuaCoCauTraLoi": "No answers yet. Ask a few questions and come back.",
  "tk.chuaCoLuotHoi": "No questions in the last 30 days.",
  "tk.khongTaiDuoc": "Could not load the statistics.",

  "kind.grounded": "Grounded in your documents",
  "kind.no_answer": "Declined — not enough grounding",
  "kind.external": "Answered from outside your documents",
  "kind.cached_external": "Reused from cache",
  "kind.chitchat": "Small talk",

  "cot.nguon": "Sources",
  "cot.hoiThoai": "Conversation",
  "cot.taiLieu": "Document",
  "cot.keoCotNguon": "Resize the sources column",
  "cot.keoCotTaiLieu": "Resize the document column",
  "chip.xemDoanGoc": "Show the original passage",
  "chip.khongTonTai": "This citation does not exist",
  "chip.nguonDaXoa": "The source of this citation has been deleted",
  "loi.khongLuuDuoc": "Could not save the change. Try again.",
  "loi.trangHong": "Something went wrong while showing this page.",
  "loi.khongTimThayTrang": "There is no page at this address.",
  "loi.veTrangChu": "Go to the home page",
  "nb.xoaHoi": 'Delete notebook "{ten}" with all its documents and conversations?',
  "nb.xoa": "Delete notebook",
  "tk.doiMatKhau": "Change password",
  "tk.matKhauCu": "Current password",
  "tk.matKhauMoi": "New password",
  "tk.daDoiMatKhau": "Password changed. Other sessions have been signed out.",
  "tk.luu": "Save",
  "xem.huongDanChip":
    "Every claim in the answer carries a number. Click it to read the passage the answer relies on.",
  "rt.ngoai": "Processed externally",
  "rt.ngoaiMoTa":
    "Your question and the relevant passages are sent to an external service. Switch to local processing to keep everything on this machine.",
  "rt.cucBo": "Processed on this machine",
  "rt.cucBoMoTa":
    "Everything runs on this machine. Nothing is sent anywhere.",
  "tk.moTaLoaiCauTraLoi":
    "The share of answers grounded in your documents measures directly whether the system does what it promises.",
  "tk.moTaDoTre":
    "Measured on the machine currently running. Figures from a development machine do not stand in for the target machine.",
  "tk.bieuDoNhan": "Questions per day",
  "tk.luotNgay": "{ngay}: {so} questions",

  "caiDat.tieuDe": "Settings",
  "caiDat.taiKhoan": "Account",
  "chung.toiNoiDung": "Skip to content",
  "nb.tuyChon": "Notebook options",
  "chat.xuat": "Export",
  "gd.cheDoHienThi": "Appearance",
  "gd.sang": "Light",
  "gd.toi": "Dark",
  "gd.theoMay": "Auto",
  "gd.ngonNgu": "Language",
  "gd.tiengViet": "Vietnamese",
  "gd.tiengAnh": "English",
};

const BANG: Record<NgonNgu, Partial<Record<Khoa, string>>> = { vi: VI, en: EN };

/**
 * Tra một chuỗi, chèn tham số theo tên.
 *
 * Thiếu khoá ở tiếng Anh thì rơi về tiếng Việt (AC-4). Thiếu ở cả hai là lỗi
 * lập trình, và trả về chính khoá — nhưng `tsc` đã chặn ca đó từ trước rồi.
 */
export function soTrang(ngonNgu: NgonNgu, so: number): string {
  return dich(ngonNgu, so === 1 ? "chung.soTrang" : "chung.soTrangNhieu", { so });
}

export function dich(
  ngonNgu: NgonNgu,
  khoa: Khoa,
  tham?: Record<string, string | number>,
): string {
  const chuoi = BANG[ngonNgu][khoa] ?? VI[khoa] ?? khoa;
  if (!tham) return chuoi;
  return chuoi.replace(/\{(\w+)\}/g, (nguyen, ten) =>
    ten in tham ? String(tham[ten]) : nguyen,
  );
}
