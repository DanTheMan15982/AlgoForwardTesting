import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex min-h-[44px] items-center justify-center rounded-md text-sm font-medium transition-all duration-150 ease-out focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neon/60 disabled:pointer-events-none disabled:opacity-40 disabled:shadow-none motion-safe:hover:-translate-y-0.5 motion-reduce:transform-none sm:min-h-0",
  {
    variants: {
      variant: {
        default:
          "bg-neon text-slate-900 shadow-glow hover:brightness-110 hover:shadow-glowSoft",
        outline:
          "border border-neon/70 bg-transparent text-neon shadow-glowSoft hover:border-neon hover:text-white hover:bg-neon/10",
        ghost: "text-slate-300 hover:text-white hover:bg-white/5",
        danger: "border border-danger/70 bg-danger/15 text-danger shadow-glowMagenta hover:bg-danger/25 hover:text-white"
      },
      size: {
        default: "h-11 px-4 py-2 sm:h-10",
        sm: "h-8 px-3",
        lg: "h-12 px-6"
      }
    },
    defaultVariants: {
      variant: "default",
      size: "default"
    }
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
