import * as React from "react"

import { cn } from "@/lib/utils"

interface SwitchProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  checked?: boolean
  onCheckedChange?: (checked: boolean) => void
}

const Switch = React.forwardRef<HTMLButtonElement, SwitchProps>(
  ({ className, checked, onCheckedChange, ...props }, ref) => {
    return (
      <button
        role="switch"
        aria-checked={checked}
        type="button"
        onClick={() => onCheckedChange?.(!checked)}
        className={cn(
          "peer relative inline-flex h-[30px] w-[50px] shrink-0 cursor-pointer rounded-full border-0 bg-[#C7C7CC] transition-colors duration-200",
          "after:absolute after:left-[2px] after:top-[2px] after:h-[26px] after:w-[26px] after:rounded-full",
          "after:bg-white after:shadow-sm",
          "after:transition-all after:duration-200",
          checked && "bg-[#34C759] after:left-[20px] after:shadow-md",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
          "active:scale-[0.97]",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)

Switch.displayName = "Switch"

export { Switch }