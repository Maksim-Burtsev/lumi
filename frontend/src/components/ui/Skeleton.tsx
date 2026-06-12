/** Shimmer skeletons matching real card layouts (no spinners). */

export function Skeleton({ className = '' }: { className?: string }) {
  return <div aria-hidden className={`skeleton ${className}`} />;
}

/** Generic card-shaped skeleton with N text lines. */
export function SkeletonCard({ lines = 2, className = '' }: { lines?: number; className?: string }) {
  return (
    <div aria-hidden className={`card p-4 ${className}`}>
      <Skeleton className="h-4 w-2/5" />
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={`mt-2.5 h-3.5 ${i % 2 === 0 ? 'w-4/5' : 'w-3/5'}`} />
      ))}
    </div>
  );
}

export function SkeletonList({ count = 3, lines = 2 }: { count?: number; lines?: number }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <SkeletonCard key={i} lines={lines} />
      ))}
    </div>
  );
}

/** Timeline-shaped skeleton: time labels + rail + cards. */
export function SkeletonTimeline({ rows = 4 }: { rows?: number }) {
  return (
    <div aria-hidden className="relative flex flex-col gap-3 pl-16">
      <div className="absolute bottom-2 left-[52px] top-2 w-px bg-hairline" />
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="relative">
          <Skeleton className="absolute left-[-64px] top-1 h-3.5 w-10" />
          <div className="card p-3.5">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="mt-2 h-3 w-1/4" />
          </div>
        </div>
      ))}
    </div>
  );
}
