import React from "react";

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 font-semibold rounded-xl transition-all active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer whitespace-nowrap";

const variants: Record<Variant, string> = {
  primary:
    "bg-gradient-to-r from-rose-600 to-rose-500 hover:from-rose-500 hover:to-rose-400 text-white shadow-lg shadow-rose-950/40",
  secondary:
    "bg-slate-800/90 hover:bg-slate-700 text-slate-100 border border-white/10",
  outline:
    "bg-transparent hover:bg-white/5 text-slate-200 border border-white/15 hover:border-white/25",
  danger:
    "bg-rose-600 hover:bg-rose-500 text-white shadow-lg shadow-rose-950/40",
  ghost: "bg-transparent hover:bg-white/5 text-slate-300 hover:text-white",
};

const sizes: Record<Size, string> = {
  sm: "min-h-[40px] px-3 py-2 text-xs",
  md: "min-h-[44px] px-4 py-2.5 text-sm",
  lg: "min-h-[48px] px-5 py-3 text-sm",
};

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "secondary", size = "md", className = "", ...props }, ref) => (
    <button
      ref={ref}
      className={`${base} ${variants[variant]} ${sizes[size]} ${className}`}
      {...props}
    />
  )
);
Button.displayName = "Button";

export const IconButton = React.forwardRef<
  HTMLButtonElement,
  React.ButtonHTMLAttributes<HTMLButtonElement> & { label: string }
>(({ label, className = "", ...props }, ref) => (
  <button
    ref={ref}
    aria-label={label}
    title={label}
    className={`inline-flex items-center justify-center min-w-[44px] min-h-[44px] p-2.5 rounded-xl bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-white/10 transition-colors cursor-pointer disabled:opacity-50 ${className}`}
    {...props}
  />
));
IconButton.displayName = "IconButton";