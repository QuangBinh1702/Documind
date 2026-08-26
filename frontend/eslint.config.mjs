import { FlatCompat } from "@eslint/eslintrc";

const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

/**
 * Bộ quy tắc của Next (core-web-vitals + TypeScript). `npm run lint` trước đây
 * không chạy được vì không có cấu hình nào — `next lint` dừng lại ở một câu hỏi
 * tương tác và thoát với mã 1, nên các chú thích `eslint-disable` trong mã là
 * chú thích chết.
 */
const config = [
  ...compat.extends("next/core-web-vitals", "next/typescript"),
  {
    ignores: [".next/**", "node_modules/**", "next-env.d.ts"],
  },
];

export default config;
