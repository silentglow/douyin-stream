import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"

import { cn } from "@/lib/utils"

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 border border-transparent bg-clip-padding font-medium whitespace-nowrap outline-none select-none disabled:pointer-events-none disabled:opacity-40 [&_svg]:pointer-events-none [&_svg]:shrink-0 [&_svg:not([class*='size-'])]:size-4",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-primary-foreground hover:bg-primary/90 active:bg-primary/85 shadow-sm hover:shadow-md",
        secondary:
          "border border-border/60 bg-secondary text-secondary-foreground hover:bg-secondary/80 hover:border-border/80 aria-expanded:bg-secondary",
        outline:
          "border border-border/60 bg-background/80 text-foreground hover:bg-secondary/80 hover:border-border/80 aria-expanded:bg-secondary",
        ghost:
          "bg-transparent text-foreground hover:bg-secondary active:bg-secondary/80",
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/90 active:bg-destructive/85",
        ghostDestructive:
          "bg-transparent text-destructive hover:bg-destructive/10 active:bg-destructive/15",
        link: "text-primary underline-offset-4 hover:underline",
        linkSecondary: "text-muted-foreground hover:text-foreground",
      },
      size: {
        default:
          "h-11 px-6 text-[15px] font-semibold rounded-[10px] has-data-[icon=inline-end]:pr-4 has-data-[icon=inline-start]:pl-4",
        sm: "h-9 px-4 text-[13px] font-medium rounded-[8px] has-data-[icon=inline-end]:pr-3 has-data-[icon=inline-start]:pl-3 [&_svg:not([class*='size-'])]:size-3.5",
        lg: "h-12 px-8 text-[16px] font-semibold rounded-[12px] has-data-[icon=inline-end]:pr-5 has-data-[icon=inline-start]:pl-5 [&_svg:not([class*='size-'])]:size-5",
        icon: "size-10 p-0 rounded-[10px]",
        iconSm: "size-8 p-0 rounded-[8px] [&_svg:not([class*='size-'])]:size-4",
        iconLg: "size-12 p-0 rounded-[12px] [&_svg:not([class*='size-'])]:size-6",
      },
    },
    defaultVariants: {
      variant: "primary",
      size: "default",
    },
  }
)

function Button({
  className,
  variant = "primary",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(
        "transition-all duration-200 spring-ease-subtle",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/50",
        "active:scale-[0.96] active:shadow-inner",
        buttonVariants({ variant, size, className })
      )}
      {...props}
    />
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export { Button, buttonVariants }
