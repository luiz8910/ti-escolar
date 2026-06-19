import type { SVGProps } from "react";

/**
 * Conjunto mínimo de ícones de linha usados na UI do TI-Escolar.
 * Todos herdam a cor via `currentColor` (controle pelo `text-*`) e o tamanho via `size`.
 * Se preferir, troque por `lucide-react` (dependência leve) mantendo os nomes.
 */
type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function base({ size = 18, ...rest }: IconProps) {
  return {
    width: size,
    height: size,
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.7,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    ...rest,
  };
}

export const ChatBubbleIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M5 6a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2H9l-4 3V6Z" />
  </svg>
);

export const GridIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="4" y="4" width="7" height="7" rx="1.5" />
    <rect x="13" y="4" width="7" height="7" rx="1.5" />
    <rect x="4" y="13" width="7" height="7" rx="1.5" />
    <rect x="13" y="13" width="7" height="7" rx="1.5" />
  </svg>
);

export const UsersIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <circle cx="9" cy="8" r="3" />
    <path d="M4 19c0-3 2.2-5 5-5s5 2 5 5" />
    <path d="M16 6.5a3 3 0 0 1 0 5.6M18 18.5c0-2-1-3.4-2.5-4.2" />
  </svg>
);

export const CapIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M3 9l9-4 9 4-9 4-9-4Z" />
    <path d="M7 11v4c0 1.1 2.2 2 5 2s5-.9 5-2v-4" />
    <path d="M21 9v4" />
  </svg>
);

export const BookIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6 4h10a2 2 0 0 1 2 2v14H8a2 2 0 0 0-2 2V4Z" />
    <path d="M6 18h12" />
  </svg>
);

export const InstructionsIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <rect x="5" y="3" width="14" height="18" rx="2" />
    <path d="M9 8h6M9 12h6M9 16h3" />
  </svg>
);

export const BuildingIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M5 20V8l7-4 7 4v12" />
    <path d="M3 20h18M9 12h2M13 12h2M9 16h2M13 16h2" />
  </svg>
);

export const BellIcon = (p: IconProps) => (
  <svg {...base(p)}>
    <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6Z" />
    <path d="M10 19a2 2 0 0 0 4 0" />
  </svg>
);

export const ChevronDownIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M6 9l6 6 6-6" />
  </svg>
);

export const ExternalIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 1.8, ...p })}>
    <path d="M7 17L17 7M9 7h8v8" />
  </svg>
);

export const PlusIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2.2, ...p })}>
    <path d="M12 5v14M5 12h14" />
  </svg>
);

export const CheckIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2.4, ...p })}>
    <path d="M5 13l4 4L19 7" />
  </svg>
);

export const CloseIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);

export const MenuIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 2, ...p })}>
    <path d="M4 6h16M4 12h16M4 18h16" />
  </svg>
);

export const PrintIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 1.6, ...p })}>
    <path d="M7 9V4h10v5M7 18H5a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-2M7 14h10v6H7v-6Z" />
  </svg>
);

export const FileIcon = (p: IconProps) => (
  <svg {...base({ strokeWidth: 1.6, ...p })}>
    <path d="M7 3h7l5 5v13H7V3Z" />
    <path d="M14 3v5h5" />
  </svg>
);

export const SparkIcon = ({ size = 18, ...rest }: IconProps) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="currentColor" {...rest}>
    <path d="M12 3l2 5 5 1-3.5 3.5L16 18l-4-2.5L8 18l.5-5.5L5 9l5-1 2-5Z" />
  </svg>
);
