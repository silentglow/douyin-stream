import * as React from "react"

import { cn } from "@/lib/utils"

function Card({
  className,
  size = "default",
  hoverable = true,
  glass = false,
  ...props
}: React.ComponentProps<"div"> & { 
  size?: "default" | "sm" | "lg"
  hoverable?: boolean
  glass?: boolean
}) {
  return (
    <div
      data-slot="card"
      data-size={size}
      className={cn(
        "group/card flex flex-col overflow-hidden rounded-[14px] border",
        glass 
          ? "border-border/30 bg-card/80 backdrop-blur-xl" 
          : "border-border/60 bg-card",
        "text-card-foreground",
        "apple-shadow-sm",
        hoverable && "hover:-translate-y-0.5",
        "transition-all duration-300 spring-ease-subtle",
        "has-[>img:first-child]:pt-0",
        "data-[size=sm]:gap-3 data-[size=sm]:p-4",
        "data-[size=default]:gap-5 data-[size=default]:p-5",
        "data-[size=lg]:gap-6 data-[size=lg]:p-6",
        "*:[img:first-child]:rounded-t-[14px] *:[img:last-child]:rounded-b-[14px]",
        className
      )}
      {...props}
    />
  )
}

function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "group/card-header @container/card-header flex flex-col gap-2",
        "has-data-[slot=card-description]:gap-1",
        "[.border-b]:pb-3 [.border-b]:border-border/40",
        className
      )}
      {...props}
    />
  )
}

function CardTitle({ className, asChild = false, ...props }: React.ComponentProps<"div"> & { asChild?: boolean }) {
  const Component = asChild ? React.Fragment : "div"
  return (
    <Component
      data-slot="card-title"
      className={cn(
        "text-title-3 font-semibold leading-tight tracking-tight text-foreground",
        className
      )}
      {...props}
    />
  )
}

function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-body text-muted-foreground", className)}
      {...props}
    />
  )
}

function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("text-body", className)}
      {...props}
    />
  )
}

function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center gap-3 border-t border-border/40 bg-secondary/30 pt-4",
        className
      )}
      {...props}
    />
  )
}

export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardDescription,
  CardContent,
}
