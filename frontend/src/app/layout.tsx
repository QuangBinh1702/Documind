import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "DocuMind",
  description: "Hỏi đáp trên tài liệu của bạn, luôn kèm trích dẫn kiểm chứng được",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="vi">
      <body className="h-full antialiased">{children}</body>
    </html>
  );
}
