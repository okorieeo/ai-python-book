export function Sparkline({ points, width = 160, height = 36 }: { points: number[]; width?: number; height?: number }) {
  if (points.length < 2) return <svg width={width} height={height} aria-hidden />;
  const min = Math.min(...points), max = Math.max(...points), span = max - min || 1;
  const d = points.map((v, i) => `${(i / (points.length - 1)) * width},${height - 2 - ((v - min) / span) * (height - 4)}`).join(" ");
  return (
    <svg width={width} height={height} role="img" aria-label={`last ${points.length} readings`}>
      <polyline points={d} fill="none" stroke="currentColor" strokeWidth={1.5} />
    </svg>
  );
}
