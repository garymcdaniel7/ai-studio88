/**
 * Canonical Navigation Configuration — Story 115.
 *
 * ONE typed definition drives every navigation surface (desktop Sidebar,
 * mobile drawer, breadcrumbs). Consistent routes, labels, icons, ordering,
 * role-aware visibility, and active-route matching.
 *
 * Rules:
 * - Desktop and mobile show the same authorized destinations
 * - Admin/developer-only items are hidden for unauthorized users
 * - Route-level authorization remains enforced independently of visibility
 * - Generic "Training" renamed to "LoRA Training" (approved customer label)
 */

import {
  Home,
  Brain,
  Pencil,
  Users,
  Send,
  Settings,
  GraduationCap,
  FolderOpen,
  Search,
  User,
  BookOpen,
  type LucideIcon,
} from "lucide-react";

// =============================================================================
// Types
// =============================================================================

export type UserRole = "owner" | "admin" | "editor" | "viewer";

export interface NavItem {
  /** Unique key for the item */
  key: string;
  /** Customer-facing label */
  label: string;
  /** Route path */
  href: string;
  /** Lucide icon component */
  icon: LucideIcon;
  /** Minimum role required to see this item (undefined = all roles) */
  requiredRole?: UserRole;
  /** If true, item is only shown when feature flag is enabled */
  featureFlag?: string;
  /** Route aliases for active-state matching (e.g., nested routes) */
  activeAliases?: string[];
}

export interface NavSection {
  /** Section label (null for ungrouped items) */
  label: string | null;
  /** Items in this section */
  items: NavItem[];
}

// =============================================================================
// Role Hierarchy
// =============================================================================

const ROLE_HIERARCHY: Record<UserRole, number> = {
  owner: 4,
  admin: 3,
  editor: 2,
  viewer: 1,
};

export function hasRequiredRole(userRole: UserRole, requiredRole?: UserRole): boolean {
  if (!requiredRole) return true; // No requirement = visible to all
  return ROLE_HIERARCHY[userRole] >= ROLE_HIERARCHY[requiredRole];
}

// =============================================================================
// Canonical Navigation Definition
// =============================================================================

export const NAV_SECTIONS: NavSection[] = [
  {
    label: null,
    items: [
      { key: "home", label: "Home", href: "/", icon: Home },
      { key: "brain", label: "Brain", href: "/brain", icon: Brain },
      { key: "projects", label: "Projects", href: "/projects", icon: FolderOpen, activeAliases: ["/projects/"] },
    ],
  },
  {
    label: "Create",
    items: [
      { key: "studio", label: "Studio", href: "/create", icon: Pencil },
      { key: "story", label: "Story", href: "/story", icon: BookOpen },
      { key: "training", label: "LoRA Training", href: "/training", icon: GraduationCap },
    ],
  },
  {
    label: "Manage",
    items: [
      { key: "talent", label: "Talent", href: "/talent", icon: Users },
      { key: "library", label: "Library", href: "/assets", icon: Search },
    ],
  },
  {
    label: "Operate",
    items: [
      { key: "publish", label: "Publish", href: "/publish", icon: Send },
      { key: "admin", label: "Admin", href: "/admin", icon: Settings, requiredRole: "admin", activeAliases: ["/admin/"] },
      { key: "settings", label: "Settings", href: "/settings", icon: User },
    ],
  },
];

// =============================================================================
// Flat list (for mobile drawer and programmatic access)
// =============================================================================

export function getFlatNavItems(): NavItem[] {
  return NAV_SECTIONS.flatMap((section) => section.items);
}

// =============================================================================
// Filtered by role
// =============================================================================

export function getVisibleSections(userRole: UserRole): NavSection[] {
  return NAV_SECTIONS.map((section) => ({
    ...section,
    items: section.items.filter((item) => hasRequiredRole(userRole, item.requiredRole)),
  })).filter((section) => section.items.length > 0);
}

export function getVisibleFlatItems(userRole: UserRole): NavItem[] {
  return getFlatNavItems().filter((item) => hasRequiredRole(userRole, item.requiredRole));
}

// =============================================================================
// Active-route matching
// =============================================================================

export function isNavItemActive(item: NavItem, pathname: string): boolean {
  // Exact match
  if (pathname === item.href) return true;

  // Prefix match (but not for "/" which would match everything)
  if (item.href !== "/" && pathname.startsWith(item.href)) return true;

  // Alias match (for nested routes like /projects/[id])
  if (item.activeAliases) {
    for (const alias of item.activeAliases) {
      if (pathname.startsWith(alias)) return true;
    }
  }

  return false;
}
