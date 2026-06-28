interface ProgressDotsProps {
  value: number;
  max?: number;
  title?: string;
}

/** Five tiny dots — e.g. memory importance. */
export function ProgressDots({ value, max = 5, title }: ProgressDotsProps) {
  const clamped = Math.max(0, Math.min(max, Math.round(value)));
  return (
    <span className="inline-flex items-center gap-[3px]" title={title} aria-label={title ?? `${clamped}/${max}`}>
      {Array.from({ length: max }).map((_, i) => (
        <span
          key={i}
          className={`h-[5px] w-[5px] rounded-full ${i < clamped ? 'bg-accent' : 'bg-[var(--hairline)]'}`}
        />
      ))}
    </span>
  );
}
