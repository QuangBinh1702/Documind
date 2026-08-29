/**
 * Bộ icon dùng chung — nét 1.6, kích thước 16px mặc định, ăn theo `currentColor`.
 *
 * Vẽ tay theo cùng một lưới 24×24 để mọi icon trên giao diện có cùng độ dày nét
 * và cùng "giọng"; không kéo một bộ icon ngoài về chỉ để dùng mười hình.
 */

type Props = React.SVGProps<SVGSVGElement> & { size?: number };

function Goc({ size = 16, children, ...rest }: Props) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export const Bt = {
  caiDat: (p: Props) => (
    <Goc {...p}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </Goc>
  ),
  chiaSe: (p: Props) => (
    <Goc {...p}>
      <path d="M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1" />
      <path d="M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1" />
    </Goc>
  ),
  them: (p: Props) => (
    <Goc {...p}>
      <path d="M12 5v14M5 12h14" />
    </Goc>
  ),
  xoa: (p: Props) => (
    <Goc {...p}>
      <path d="M4 7h16M10 11v6M14 11v6M6 7l1 12a2 2 0 0 0 2 2h6a2 2 0 0 0 2-2l1-12M9 7V4h6v3" />
    </Goc>
  ),
  taiLen: (p: Props) => (
    <Goc {...p}>
      <path d="M12 16V4M6 10l6-6 6 6M4 20h16" />
    </Goc>
  ),
  gui: (p: Props) => (
    <Goc {...p}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </Goc>
  ),
  /** Ô vuông đặc — quy ước "dừng" quen thuộc, khác hẳn hình mũi tên "gửi". */
  dung: (p: Props) => (
    <Goc {...p}>
      <rect x="7" y="7" width="10" height="10" rx="2" fill="currentColor" stroke="none" />
    </Goc>
  ),
  toanCau: (p: Props) => (
    <Goc {...p}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3z" />
    </Goc>
  ),
  chep: (p: Props) => (
    <Goc {...p}>
      <rect x="9" y="9" width="11" height="11" rx="2" />
      <path d="M5 15V5a2 2 0 0 1 2-2h10" />
    </Goc>
  ),
  kiem: (p: Props) => (
    <Goc {...p}>
      <path d="M5 12l5 5L20 7" />
    </Goc>
  ),
  xuat: (p: Props) => (
    <Goc {...p}>
      <path d="M12 4v12M7 11l5 5 5-5M4 20h16" />
    </Goc>
  ),
  mui: (p: Props) => (
    <Goc {...p}>
      <path d="M6 9l6 6 6-6" />
    </Goc>
  ),
  quayLai: (p: Props) => (
    <Goc {...p}>
      <path d="M19 12H5M11 18l-6-6 6-6" />
    </Goc>
  ),
  dong: (p: Props) => (
    <Goc {...p}>
      <path d="M6 6l12 12M18 6L6 18" />
    </Goc>
  ),
  thongKe: (p: Props) => (
    <Goc {...p}>
      <path d="M4 20h16M7 16V9M12 16V4M17 16v-6" />
    </Goc>
  ),
  khoa: (p: Props) => (
    <Goc {...p}>
      <rect x="5" y="11" width="14" height="10" rx="2" />
      <path d="M8 11V7a4 4 0 0 1 8 0v4" />
    </Goc>
  ),
  ra: (p: Props) => (
    <Goc {...p}>
      <path d="M10 4H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h4M15 8l5 4-5 4M20 12H9" />
    </Goc>
  ),
  tep: (p: Props) => (
    <Goc {...p}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5M9 13h6M9 17h6" />
    </Goc>
  ),
  anh: (p: Props) => (
    <Goc {...p}>
      <rect x="4" y="5" width="16" height="14" rx="2" />
      <circle cx="9" cy="10" r="1.5" />
      <path d="M20 16l-5-5-7 8" />
    </Goc>
  ),
  matTroi: (p: Props) => (
    <Goc {...p}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </Goc>
  ),
  trang: (p: Props) => (
    <Goc {...p}>
      <path d="M20 14.5A8 8 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5z" />
    </Goc>
  ),
  manHinh: (p: Props) => (
    <Goc {...p}>
      <rect x="3" y="4" width="18" height="12" rx="2" />
      <path d="M8 20h8M12 16v4" />
    </Goc>
  ),
  nhieuHon: (p: Props) => (
    <Goc {...p}>
      <circle cx="5" cy="12" r="1.2" fill="currentColor" />
      <circle cx="12" cy="12" r="1.2" fill="currentColor" />
      <circle cx="19" cy="12" r="1.2" fill="currentColor" />
    </Goc>
  ),
};
