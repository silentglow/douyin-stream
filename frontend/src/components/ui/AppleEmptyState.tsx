import { motion } from 'framer-motion';

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
    <motion.div
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: 'spring', stiffness: 400, damping: 30 }}
      className="flex flex-col items-center justify-center py-16 min-h-[400px]"
    >
      <motion.div
        initial={{ scale: 0.9 }}
        animate={{ scale: 1 }}
        transition={{ type: 'spring', stiffness: 300, damping: 20, delay: 0.05 }}
        className="text-muted-foreground/30"
      >
        {icon}
      </motion.div>
      <h3 className="text-xl font-semibold text-muted-foreground mt-4">
        {title}
      </h3>
      {description && (
        <p className="text-sm text-muted-foreground/70 mt-1.5 text-center max-w-[280px]">
          {description}
        </p>
      )}
      {action && <div className="mt-5">{action}</div>}
    </motion.div>
  );
}
