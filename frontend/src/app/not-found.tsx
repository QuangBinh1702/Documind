"use client";

import Link from "next/link";
import { useNgonNgu } from "@/components/NgonNguProvider";

export default function KhongTimThay() {
  const { t } = useNgonNgu();
  return (
    <main className="grid h-full place-items-center px-6 text-center">
      <div>
        <p className="font-medium">{t("loi.khongTimThayTrang")}</p>
        <Link href="/" className="mt-3 inline-block text-sm text-nhan underline">
          {t("loi.veTrangChu")}
        </Link>
      </div>
    </main>
  );
}
