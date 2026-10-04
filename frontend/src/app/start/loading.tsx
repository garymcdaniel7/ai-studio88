export default function Loading() {
  return (
    <main aria-label="Loading START" className="mx-auto w-full max-w-6xl space-y-6">
      <div className="h-8 w-56 animate-pulse rounded bg-white/[0.08]" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        {["projects", "assets", "generations"].map((label) => (
          <div className="h-24 animate-pulse rounded-xl border border-white/[0.06] bg-white/[0.03]" key={label} />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {["project-a", "project-b"].map((label) => (
          <div className="h-40 animate-pulse rounded-xl border border-white/[0.06] bg-white/[0.03]" key={label} />
        ))}
      </div>
    </main>
  );
}
