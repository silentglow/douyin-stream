export function SkeletonScreen() {
  return (
    <div className="h-full w-full bg-background p-6 max-sm:p-4 max-sm:pb-20 overflow-y-auto">
      <div className="apple-skeleton h-8 w-48 rounded-lg mb-6" />
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4 max-sm:gap-3">
        {[...Array(8)].map((_, i) => (
          <div
            key={i}
            className="apple-skeleton rounded-[22px]"
            style={{
              gridColumn: i >= 6 ? 'span 4' : i >= 4 ? 'span 2' : 'span 1',
              minHeight: i >= 6 ? 180 : i >= 4 ? 160 : 140,
            }}
          />
        ))}
      </div>
    </div>
  );
}
