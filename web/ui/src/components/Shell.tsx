import type { ReactNode } from "react";
import { GridIcon, StoreIcon, PlusIcon, ShareIcon, GearIcon } from "./Icons";

type Section = "dashboard" | "catalog" | "custom" | "shares" | "settings";

const NAV: { id: Section; label: string; icon: typeof GridIcon }[] = [
  { id: "dashboard", label: "Dashboard", icon: GridIcon },
  { id: "catalog", label: "Catalog", icon: StoreIcon },
  { id: "custom", label: "Custom pod", icon: PlusIcon },
  { id: "shares", label: "Shares", icon: ShareIcon },
];

export function Shell({
  active,
  children,
}: {
  active: Section;
  children: ReactNode;
}) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand__mark" />
          <div className="brand__name">
            Pod<span>scale</span>
          </div>
        </div>
        {NAV.map(({ id, label, icon: Icon }) => (
          <a
            key={id}
            className={"nav-item" + (id === active ? " nav-item--active" : "")}
            aria-current={id === active ? "page" : undefined}
          >
            <Icon className="nav-icon" />
            {label}
          </a>
        ))}
        <div className="spacer" />
        <a className="nav-item">
          <GearIcon className="nav-icon" />
          Settings
        </a>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
