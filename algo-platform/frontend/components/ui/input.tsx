import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      type={type}
      className={cn(
      "flex h-11 w-full rounded-md border border-border/80 bg-panelSoft/70 px-3 py-2 text-sm text-slate-100 placeholder:text-slate-500 shadow-[inset_0_0_0_1px_rgba(0,240,255,0.04)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-neon/60 focus-visible:border-neon/60 sm:h-10",
        className
      )}
      ref={ref}
      {...props}
    />
  )
);
Input.displayName = "Input";

export { Input };
