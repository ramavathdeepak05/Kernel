"use client";

import * as React from "react";
import { Steps } from "@ark-ui/react/steps";
import { cn } from "@/lib/utils";

// ── Stepper Root ─────────────────────────────────────────────────────────

const Stepper = React.forwardRef<
  React.ElementRef<typeof Steps.Root>,
  React.ComponentPropsWithoutRef<typeof Steps.Root>
>(({ className, ...props }, ref) => (
  <Steps.Root
    ref={ref}
    className={cn("w-full", className)}
    {...props}
  />
));
Stepper.displayName = "Stepper";

// ── Stepper List ─────────────────────────────────────────────────────────

const StepperList = React.forwardRef<
  React.ElementRef<typeof Steps.List>,
  React.ComponentPropsWithoutRef<typeof Steps.List>
>(({ className, ...props }, ref) => (
  <Steps.List
    ref={ref}
    className={cn("flex justify-between items-start gap-1 w-full", className)}
    {...props}
  />
));
StepperList.displayName = "StepperList";

// ── Stepper Item ─────────────────────────────────────────────────────────

const StepperItem = React.forwardRef<
  React.ElementRef<typeof Steps.Item>,
  React.ComponentPropsWithoutRef<typeof Steps.Item>
>(({ className, ...props }, ref) => (
  <Steps.Item
    ref={ref}
    className={cn("relative flex flex-col items-center flex-1", className)}
    {...props}
  />
));
StepperItem.displayName = "StepperItem";

// ── Stepper Trigger ──────────────────────────────────────────────────────

const StepperTrigger = React.forwardRef<
  React.ElementRef<typeof Steps.Trigger>,
  React.ComponentPropsWithoutRef<typeof Steps.Trigger>
>(({ className, ...props }, ref) => (
  <Steps.Trigger
    ref={ref}
    className={cn(
      "w-full flex flex-col items-center gap-2 text-left rounded-md group outline-none",
      className
    )}
    {...props}
  />
));
StepperTrigger.displayName = "StepperTrigger";

// ── Stepper Indicator ───────────────────────────────────────────────────

const StepperIndicator = React.forwardRef<
  React.ElementRef<typeof Steps.Indicator>,
  React.ComponentPropsWithoutRef<typeof Steps.Indicator>
>(({ className, ...props }, ref) => (
  <Steps.Indicator
    ref={ref}
    className={cn(
      "flex justify-center items-center shrink-0 rounded-full font-semibold w-8 h-8 text-sm border-2 transition-colors duration-200",
      "data-complete:bg-blue-600 data-complete:text-white data-complete:border-blue-600",
      "data-current:bg-blue-600 data-current:text-white data-current:border-blue-600",
      "data-incomplete:bg-slate-100 data-incomplete:text-slate-500 data-incomplete:border-slate-200",
      "dark:data-incomplete:bg-slate-800 dark:data-incomplete:text-slate-400 dark:data-incomplete:border-slate-700",
      className
    )}
    {...props}
  />
));
StepperIndicator.displayName = "StepperIndicator";

// ── Stepper Separator ───────────────────────────────────────────────────

const StepperSeparator = React.forwardRef<
  React.ElementRef<typeof Steps.Separator>,
  React.ComponentPropsWithoutRef<typeof Steps.Separator>
>(({ className, ...props }, ref) => (
  <Steps.Separator
    ref={ref}
    className={cn(
      "flex-1 h-0.5 mx-3 transition-colors duration-200",
      "bg-slate-200 dark:bg-slate-700",
      "data-complete:bg-blue-600",
      className
    )}
    {...props}
  />
));
StepperSeparator.displayName = "StepperSeparator";

// ── Segment Indicator (For horizontal lines without numbers) ─────────────

const StepperSegmentIndicator = React.forwardRef<
  React.ElementRef<typeof Steps.Indicator>,
  React.ComponentPropsWithoutRef<typeof Steps.Indicator>
>(({ className, ...props }, ref) => (
  <Steps.Indicator
    ref={ref}
    className={cn(
      "w-full shrink-0 h-1.5 rounded-full transition-colors duration-200",
      "data-complete:bg-blue-600",
      "data-current:bg-blue-600",
      "data-incomplete:bg-slate-200 dark:data-incomplete:bg-slate-700",
      className
    )}
    {...props}
  />
));
StepperSegmentIndicator.displayName = "StepperSegmentIndicator";

export {
  Stepper,
  StepperList,
  StepperItem,
  StepperTrigger,
  StepperIndicator,
  StepperSegmentIndicator,
  StepperSeparator,
};