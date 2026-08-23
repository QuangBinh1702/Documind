"""Cấu hình mà giao diện cần biết — US-030, US-032.

Chỉ phơi ra thứ **người dùng** cần: dữ liệu có rời khỏi máy không. Không phơi
tên mô hình, tên nhà cung cấp hay tên cờ cấu hình.

Lý do là một bài học phải trả giá: bản đầu tiên hiện thẳng
`ollama-cloud:gemma4:31b` và chữ *"Privacy Mode"* lên giao diện. Cả hai đều là
ngôn ngữ của người viết mã. Người dùng không biết `gemma4:31b` là gì, không biết
`Privacy Mode` là tên một biến trong `.env`, và không làm gì được với hai thông
tin đó — nhưng vẫn phải đọc chúng ở mọi câu trả lời.

Tên mô hình vẫn được ghi đầy đủ ở nơi nó có ích: log máy chủ, cột `model_used`
của `chat_messages`, và siêu dữ liệu của mỗi lượt chạy đánh giá.
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.api.deps import CurrentUser
from app.settings import settings

router = APIRouter(tags=["config"])


class CauHinhNguoiDung(BaseModel):
    du_lieu_roi_khoi_may: bool = Field(
        description="Câu hỏi và các đoạn tài liệu có được gửi ra dịch vụ bên "
                    "ngoài không. Đây là thứ duy nhất về mô hình mà người dùng "
                    "thật sự cần biết."
    )
    che_do: str = Field(description="'nhanh' hoặc 'rieng-tu' — để giao diện đặt nhãn")


@router.get("/config", response_model=CauHinhNguoiDung,
            summary="Cấu hình hiển thị cho người dùng")
def cau_hinh(_: CurrentUser) -> CauHinhNguoiDung:
    """Đòi đăng nhập: đây là thông tin về cách máy chủ xử lý dữ liệu của một
    tài khoản, không phải thông tin công khai."""
    rieng_tu = settings.default_mode == "privacy"
    return CauHinhNguoiDung(
        du_lieu_roi_khoi_may=not rieng_tu,
        che_do="rieng-tu" if rieng_tu else "nhanh",
    )
