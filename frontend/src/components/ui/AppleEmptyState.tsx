interface AppleEmptyStateProps {
  icon: React.ReactNode;
  title: string;
  description?: string;
  action?: React.ReactNode;
}

export function AppleEmptyState({
  icon,
  title,
  description,
  action,
}: AppleEmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-[60px] min-h-[400px]">
      <div className="text-muted-foreground/40">{icon}</div>
      <h3 className="text-[20px] font-semibold text-[#8E8E93] mt-3">
        {title}
      </h3>
      {description && (
        <p className="text-[13px] text-muted-foreground mt-1 text-center">
          {description}
        </p>
      )}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}
