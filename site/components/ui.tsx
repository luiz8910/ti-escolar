/** Blocos de layout e tipografia reutilizados pelas seções da landing page. */
import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export function Container({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cn("mx-auto w-full max-w-content px-5 sm:px-6 lg:px-8", className)}>
      {children}
    </div>
  );
}

export function Section({
  id,
  children,
  className,
  tone = "light",
}: {
  id?: string;
  children: ReactNode;
  className?: string;
  /** `light` = branco · `muted` = cinza de fundo · `brand` = azul escuro. */
  tone?: "light" | "muted" | "brand";
}) {
  const tones = {
    light: "bg-surface",
    muted: "bg-n-50",
    brand: "bg-brand-900 text-white",
  } as const;

  return (
    <section id={id} className={cn("py-16 sm:py-20 lg:py-24", tones[tone], className)}>
      <Container>{children}</Container>
    </section>
  );
}

export function Eyebrow({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p
      className={cn(
        "mb-3 text-xs font-bold uppercase tracking-[0.14em] text-brand-600",
        className,
      )}
    >
      {children}
    </p>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  description,
  align = "center",
  invert = false,
}: {
  eyebrow?: string;
  title: string;
  description?: ReactNode;
  align?: "center" | "left";
  /** Em fundo escuro, inverte as cores do texto. */
  invert?: boolean;
}) {
  return (
    <div className={cn("max-w-2xl", align === "center" && "mx-auto text-center")}>
      {eyebrow && <Eyebrow className={invert ? "text-brand-200" : undefined}>{eyebrow}</Eyebrow>}
      <h2
        className={cn(
          "text-balance text-2xl font-extrabold tracking-tight sm:text-3xl lg:text-[2.125rem]",
          invert ? "text-white" : "text-n-900",
        )}
      >
        {title}
      </h2>
      {description && (
        <p
          className={cn(
            "mt-4 text-base leading-relaxed sm:text-lg",
            invert ? "text-brand-100" : "text-n-600",
          )}
        >
          {description}
        </p>
      )}
    </div>
  );
}

type CtaProps = {
  href: string;
  children: ReactNode;
  variant?: "primary" | "secondary" | "ghost" | "onDark";
  size?: "md" | "lg";
  className?: string;
  external?: boolean;
};

/** Link com aparência de botão — a LP não tem ações, só navegação. */
export function Cta({
  href,
  children,
  variant = "primary",
  size = "md",
  className,
  external = false,
}: CtaProps) {
  const variants = {
    primary: "bg-brand-600 text-white shadow-sm hover:bg-brand-700",
    secondary: "bg-white text-n-800 border border-n-300 hover:bg-n-50",
    ghost: "text-brand-600 hover:bg-brand-50",
    onDark: "bg-white text-brand-700 shadow-sm hover:bg-brand-50",
  } as const;

  const sizes = {
    md: "h-11 px-5 text-sm",
    lg: "h-12 px-6 text-[0.95rem]",
  } as const;

  return (
    <a
      href={href}
      {...(external ? { target: "_blank", rel: "noopener noreferrer" } : {})}
      className={cn(
        "inline-flex select-none items-center justify-center gap-2 rounded-md font-semibold transition-colors",
        variants[variant],
        sizes[size],
        className,
      )}
    >
      {children}
    </a>
  );
}

export function FeatureCard({
  icon,
  title,
  children,
}: {
  icon: ReactNode;
  title: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-lg border border-n-200 bg-surface p-6 shadow-sm transition-shadow hover:shadow-md">
      <div className="mb-4 inline-flex h-11 w-11 items-center justify-center rounded-md bg-brand-50 text-brand-600">
        {icon}
      </div>
      <h3 className="mb-2 text-base font-bold text-n-900">{title}</h3>
      <p className="text-sm leading-relaxed text-n-600">{children}</p>
    </div>
  );
}
