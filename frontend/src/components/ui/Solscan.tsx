import type { ReactNode } from "react";

import Icon from "./Icon";

type Props = {
  href?: string;
  children?: ReactNode;
};

export default function Solscan({ href, children = "Solscan" }: Props) {
  const interactive = Boolean(href);
  return (
    <a
      href={href ?? "#"}
      target={interactive ? "_blank" : undefined}
      rel={interactive ? "noreferrer" : undefined}
      onClick={interactive ? undefined : (e) => e.preventDefault()}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: 4,
        fontSize: 11,
        color: "var(--tx-2)",
        textDecoration: "none",
        fontFamily: "var(--font-mono)",
      }}
    >
      {children}
      <Icon name="external" size={11} stroke={1.4} />
    </a>
  );
}
