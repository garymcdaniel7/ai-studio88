import Link from "next/link";

export type AdminTab = "dashboard" | "health" | "fleet" | "keys" | "planner";

const TABS: { key: AdminTab; href: string; label: string }[] = [
  { key: "dashboard", href: "/admin", label: "Dashboard" },
  { key: "health", href: "/admin/health", label: "Health" },
  { key: "fleet", href: "/admin/fleet", label: "Fleet / GPU" },
  { key: "planner", href: "/admin/fleet-planner", label: "Demand Planner" },
  { key: "keys", href: "/admin/keys", label: "API Keys" },
];

const INACTIVE_CLASSES =
  "border-transparent text-content-tertiary hover:text-content-secondary hover:border-gray-600";
const ACTIVE_CLASSES = "border-purple-500 text-status-info";

/**
 * Shared tab navigation across the admin section pages.
 * The Settings entry links out of /admin and can never be active here.
 */
export function AdminTabs({ active }: { active: AdminTab }) {
  return (
    <div className="flex gap-1 border-b border-border-subtle pb-px">
      {TABS.map((tab) => (
        <Link
          key={tab.key}
          href={tab.href}
          className={`px-4 py-2 text-sm font-medium border-b-2 ${
            active === tab.key ? ACTIVE_CLASSES : INACTIVE_CLASSES
          }`}
        >
          {tab.label}
        </Link>
      ))}
      <Link
        href="/settings"
        className={`px-4 py-2 text-sm font-medium border-b-2 ${
          INACTIVE_CLASSES
        }`}
      >
        Settings
      </Link>
    </div>
  );
}
