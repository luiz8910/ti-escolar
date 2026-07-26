/**
 * Ícones de linha da landing page.
 * Mesma linguagem visual do painel (`web/components/ui/icons.tsx`): traço de
 * 1.6, `currentColor` e tamanho controlado por prop.
 */
import type { SVGProps } from "react";

export type IconProps = SVGProps<SVGSVGElement> & {
  size?: number;
  strokeWidth?: number;
};

const base = ({ size = 20, strokeWidth = 1.6, ...rest }: IconProps) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  "aria-hidden": true,
  focusable: false,
  ...rest,
});

export const ChatBubbleIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M21 11.5a7.5 7.5 0 0 1-7.5 7.5H8l-4 3v-3.6A7.5 7.5 0 0 1 8.5 4h5A7.5 7.5 0 0 1 21 11.5Z" />
  </svg>
);

export const SparkIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3l1.8 4.9L18.5 9.8 13.8 11.6 12 16.5l-1.8-4.9L5.5 9.8l4.7-1.9L12 3Z" />
    <path d="M18.5 15.5l.8 2 2 .8-2 .8-.8 2-.8-2-2-.8 2-.8.8-2Z" />
  </svg>
);

export const SendIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M21 3 10.5 13.5" />
    <path d="M21 3l-6.8 18-3.7-7.5L3 9.8 21 3Z" />
  </svg>
);

export const UsersIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="9" cy="8" r="3.2" />
    <path d="M3 19c0-3 2.7-5 6-5s6 2 6 5" />
    <path d="M16.5 6.2a3 3 0 0 1 0 5.6" />
    <path d="M18 19c0-2-.8-3.5-2-4.4" />
  </svg>
);

export const FileIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M14 3H7a1.5 1.5 0 0 0-1.5 1.5v15A1.5 1.5 0 0 0 7 21h10a1.5 1.5 0 0 0 1.5-1.5V7.5L14 3Z" />
    <path d="M14 3v4.5h4.5" />
    <path d="M9 13h6M9 16.5h4" />
  </svg>
);

export const PrintIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M7 9V3.5h10V9" />
    <rect x="3.5" y="9" width="17" height="7" rx="1.5" />
    <path d="M7 14h10v6.5H7z" />
  </svg>
);

export const ShieldIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M12 3l7 3v5.5c0 4.2-2.9 7.6-7 9.5-4.1-1.9-7-5.3-7-9.5V6l7-3Z" />
    <path d="m9.2 12 2 2 3.6-3.8" />
  </svg>
);

export const BellIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M18 9a6 6 0 1 0-12 0c0 5-2 6-2 6h16s-2-1-2-6Z" />
    <path d="M13.7 20a2 2 0 0 1-3.4 0" />
  </svg>
);

export const CapIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M3 9l9-4 9 4-9 4-9-4Z" />
    <path d="M7 11v4c0 1.1 2.2 2 5 2s5-.9 5-2v-4" />
    <path d="M21 9v4" />
  </svg>
);

export const CheckIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="m5 12.5 4.5 4.5L19 7" />
  </svg>
);

export const ArrowRightIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M4 12h15" />
    <path d="m13 6 6 6-6 6" />
  </svg>
);

export const MenuIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </svg>
);

export const CloseIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M6 6l12 12M18 6 6 18" />
  </svg>
);

export const MailIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="m3.5 7 8.5 6 8.5-6" />
  </svg>
);

export const PhoneIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M7 3.5h3l1.5 4-2 1.5a11 11 0 0 0 5.5 5.5l1.5-2 4 1.5v3a2 2 0 0 1-2.2 2A16.5 16.5 0 0 1 5 5.7 2 2 0 0 1 7 3.5Z" />
  </svg>
);

/** Glifo do WhatsApp — usado só onde o canal é citado explicitamente. */
export const WhatsAppIcon = ({ size = 20, ...rest }: IconProps) => (
  <svg
    width={size}
    height={size}
    viewBox="0 0 24 24"
    fill="currentColor"
    aria-hidden
    focusable="false"
    {...rest}
  >
    <path d="M12.04 2c-5.5 0-9.96 4.46-9.96 9.96 0 1.76.46 3.48 1.34 5L2 22l5.16-1.35a9.92 9.92 0 0 0 4.88 1.25h.01c5.5 0 9.96-4.46 9.96-9.96S17.54 2 12.04 2Zm0 18.2h-.01a8.26 8.26 0 0 1-4.2-1.15l-.3-.18-3.12.82.83-3.04-.2-.31a8.24 8.24 0 0 1-1.26-4.38c0-4.56 3.71-8.27 8.27-8.27a8.27 8.27 0 0 1 0 16.53Zm4.53-6.19c-.25-.12-1.47-.72-1.69-.81-.23-.08-.4-.12-.56.13-.16.24-.64.8-.78.97-.15.16-.29.18-.53.06-.25-.12-1.05-.39-1.99-1.23-.74-.65-1.23-1.46-1.38-1.71-.14-.24-.01-.37.11-.5.11-.11.25-.29.37-.43.13-.15.17-.25.25-.41.09-.17.04-.31-.02-.43-.06-.12-.56-1.34-.76-1.84-.2-.48-.4-.42-.56-.43h-.47c-.16 0-.43.06-.65.31-.22.24-.85.83-.85 2.03s.87 2.35.99 2.51c.12.16 1.72 2.62 4.16 3.68.58.25 1.03.4 1.39.51.58.19 1.11.16 1.53.1.47-.07 1.47-.6 1.67-1.18.21-.58.21-1.07.15-1.18-.06-.11-.22-.17-.47-.29Z" />
  </svg>
);
