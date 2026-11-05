"use client";

import { Tooltip as RadixTooltip } from "@radix-ui/themes";
import React from "react";

export interface TooltipProps {
  /** The content to display inside the tooltip bubble. */
  content: React.ReactNode;
  /** The single element that triggers the tooltip on hover or focus. */
  children: React.ReactElement;
  /** Placement side of the tooltip relative to the target. */
  side?: "top" | "right" | "bottom" | "left";
  /** Alignment of the tooltip along the chosen side. */
  align?: "start" | "center" | "end";
  /** Delay in milliseconds before the tooltip appears. Default is 150ms. */
  delayDuration?: number;
  /** When true or when content is empty, tooltip does not render. */
  disabled?: boolean;
  /** Optional class name to pass to the tooltip content. */
  className?: string;
  /** Optional custom container element. */
  container?: HTMLElement | null;
}

/**
 * Enhanced Tooltip component integrating @radix-ui/themes with BackseatCaster dark gaming aesthetic.
 * Automatically handles empty content, disabled states, and clean portal rendering.
 */
export const Tooltip: React.FC<TooltipProps> = ({
  content,
  children,
  side = "top",
  align = "center",
  delayDuration = 150,
  disabled = false,
  className,
  container,
}) => {
  if (
    disabled ||
    content === null ||
    content === undefined ||
    content === false ||
    content === ""
  ) {
    return children;
  }

  return (
    <RadixTooltip
      content={
        <div className={`max-w-xs text-xs font-normal leading-relaxed text-slate-200 select-text ${className || ""}`}>
          {content}
        </div>
      }
      side={side}
      align={align}
      delayDuration={delayDuration}
      container={container}
    >
      {children}
    </RadixTooltip>
  );
};

export interface TruncatedTextProps {
  /** The full text string to display and wrap with a tooltip. */
  text: string;
  /** Number of lines before truncating. Default is 1. */
  lines?: 1 | 2 | 3;
  /** Additional Tailwind or CSS classes. */
  className?: string;
  /** HTML element tag to render as. Default is 'span'. */
  as?: "span" | "p" | "h1" | "h2" | "h3" | "h4" | "div";
  /** Placement side for the tooltip. Default is 'top'. */
  side?: "top" | "right" | "bottom" | "left";
  /** Optional custom title or prefix in the tooltip. */
  tooltipTitle?: string;
}

/**
 * Text wrapper that truncates long text (1-line or multi-line clamp)
 * and automatically attaches a rich Tooltip so users never lose long text.
 */
export const TruncatedText: React.FC<TruncatedTextProps> = ({
  text,
  lines = 1,
  className = "",
  as: Component = "span",
  side = "top",
  tooltipTitle,
}) => {
  if (!text) return null;

  const clampClass =
    lines === 1
      ? "truncate block"
      : lines === 2
      ? "line-clamp-2 block"
      : "line-clamp-3 block";

  const tooltipBody = tooltipTitle ? (
    <div className="space-y-0.5">
      <div className="text-[10px] uppercase font-bold tracking-wider text-rose-400">
        {tooltipTitle}
      </div>
      <div>{text}</div>
    </div>
  ) : (
    text
  );

  return (
    <Tooltip content={tooltipBody} side={side}>
      <Component className={`${clampClass} ${className}`}>{text}</Component>
    </Tooltip>
  );
};