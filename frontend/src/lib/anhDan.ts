/**
 * Lấy ảnh ra khỏi clipboard — US-025 AC-3.
 *
 * Dùng chung cho hai chỗ dán: cột nguồn (dán vào bất cứ đâu trên trang để thêm
 * tài liệu) và ô soạn câu hỏi (dán để hỏi ngay trên ảnh vừa chụp). Cùng một
 * thao tác của người dùng thì phải cho ra cùng một tệp, kể cả cách đặt tên.
 *
 * **Tên tệp là phần dễ bỏ sót.** Ảnh chụp màn hình không có tên: `getAsFile()`
 * trả về một `File` tên "image.png" hoặc rỗng. Đặt tên theo thời điểm dán để
 * danh sách nguồn còn phân biệt được nhiều ảnh dán liên tiếp với nhau — nếu
 * không thì người dùng nhìn thấy ba dòng "image.png" giống hệt nhau.
 */

export function anhTuClipboard(data: DataTransfer | null): File[] {
  return Array.from(data?.items ?? [])
    .filter((it) => it.kind === "file" && it.type.startsWith("image/"))
    .map((it) => it.getAsFile())
    .filter((f): f is File => f !== null)
    .map((f, i) => {
      const duoi = f.type.split("/")[1]?.replace("jpeg", "jpg") ?? "png";
      const dau = new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-");
      return new File([f], `anh-dan-${dau}${i ? `-${i + 1}` : ""}.${duoi}`, {
        type: f.type,
      });
    });
}
