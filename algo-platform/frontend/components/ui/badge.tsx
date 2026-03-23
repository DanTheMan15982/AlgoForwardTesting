import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold tracking-wide",
  {
    variants: {
      variant: {
        default: "bg-panelSoft text-slate-200 border border-border/70",
        success: "bg-success/15 text-success border border-success/40",
        warning: "bg-warn/15 text-warn border border-warn/40",
        danger: "bg-danger/15 text-danger border border-danger/40",
        info: "bg-neon/15 text-neon border border-neon/40",
        magenta: "bg-neonMagenta/15 text-neonMagenta border border-neonMagenta/40"
      }
    },
    defaultVariants: {
      variant: "default"
    }
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
