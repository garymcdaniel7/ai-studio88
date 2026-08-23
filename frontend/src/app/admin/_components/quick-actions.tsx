import Link from "next/link";
import { DollarSign, Shield, Settings } from "lucide-react";

/**
 * Quick-action cards linking out to costs, fleet reputation and API keys.
 */
export function QuickActions() {
  return (
    <div className="grid grid-cols-3 gap-4">
      <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
        <DollarSign className="h-6 w-6 text-status-success mb-3" />
        <h3 className="text-sm font-semibold text-content-primary">Cost Controls</h3>
        <p className="text-xs text-content-muted mt-1">Budget limits, spend tracking, alerts</p>
        <Link href="/analytics" className="mt-3 inline-block rounded-lg bg-status-success-muted px-3 py-1.5 text-xs text-status-success hover:bg-green-600/30">
          View Costs
        </Link>
      </div>
      <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
        <Shield className="h-6 w-6 text-status-warning mb-3" />
        <h3 className="text-sm font-semibold text-content-primary">Provider Reputation</h3>
        <p className="text-xs text-content-muted mt-1">Host reliability, blacklist, preferred hosts</p>
        <Link href="/admin/fleet" className="mt-3 inline-block rounded-lg bg-status-warning-muted px-3 py-1.5 text-xs text-status-warning hover:bg-amber-600/30">
          View Reputation
        </Link>
      </div>
      <div className="rounded-xl border border-border-subtle bg-surface-raised p-5">
        <Settings className="h-6 w-6 text-status-info mb-3" />
        <h3 className="text-sm font-semibold text-content-primary">API Keys</h3>
        <p className="text-xs text-content-muted mt-1">Manage ElevenLabs, OpenAI, and other keys</p>
        <Link href="/settings" className="mt-3 inline-block rounded-lg bg-status-info-muted px-3 py-1.5 text-xs text-status-info hover:bg-purple-600/30">
          Configure in Settings
        </Link>
      </div>
    </div>
  );
}
