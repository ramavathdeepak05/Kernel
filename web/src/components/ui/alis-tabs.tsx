/**
 * ALISTabs — Obsidian Editorial tab system
 * Black/White/Green palette · Spring-physics animated indicator
 * Wraps Radix Tabs.
 */

import * as React from "react";
import * as TabsPrimitive from "@radix-ui/react-tabs";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

const ALISTabs = TabsPrimitive.Root;

const ALISTabsList = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.List>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.List>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.List
    ref={ref}
    className={cn(
      "relative flex gap-0.5 border-b pb-0",
      className,
    )}
    style={{ borderColor: "rgba(0,0,0,0.08)" }}
    {...props}
  />
));
ALISTabsList.displayName = "ALISTabsList";

interface ALISTabsTriggerProps extends React.ComponentPropsWithoutRef<typeof TabsPrimitive.Trigger> {
  badge?: number;
}

const ALISTabsTrigger = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Trigger>,
  ALISTabsTriggerProps
>(({ className, badge, children, ...props }, ref) => (
  <TabsPrimitive.Trigger
    ref={ref}
    className={cn(
      "group relative px-4 py-2.5 text-[11px] font-semibold tracking-wide transition-all duration-150",
      "text-[#aaaaaa] hover:text-[#333333]",
      "data-[state=active]:text-[#0a0a0a]",
      "outline-none cursor-pointer bg-transparent border-none uppercase letter-spacing-widest",
      className,
    )}
    style={{ letterSpacing: "0.06em" }}
    {...props}
  >
    {/* Active green underline — rendered via after pseudo via data attr */}
    <span
      className="absolute bottom-0 left-0 right-0 h-[2px] rounded-full transition-all duration-200 opacity-0 group-data-[state=active]:opacity-100"
      style={{ background: "#1D9E75" }}
      aria-hidden
    />

    <span className="relative z-10 flex items-center gap-1.5">
      {children}
      <AnimatePresence mode="popLayout">
        {badge != null && badge > 0 && (
          <motion.span
            key={badge}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 500, damping: 25 }}
            className="inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full text-[8px] font-bold"
            style={{
              background: "rgba(29,158,117,0.14)",
              color: "#1D9E75",
              border: "0.5px solid rgba(29,158,117,0.32)",
            }}
          >
            {badge}
          </motion.span>
        )}
      </AnimatePresence>
    </span>
  </TabsPrimitive.Trigger>
));
ALISTabsTrigger.displayName = "ALISTabsTrigger";

const ALISTabsContent = React.forwardRef<
  React.ElementRef<typeof TabsPrimitive.Content>,
  React.ComponentPropsWithoutRef<typeof TabsPrimitive.Content>
>(({ className, ...props }, ref) => (
  <TabsPrimitive.Content
    ref={ref}
    className={cn("mt-4 outline-none", className)}
    {...props}
  />
));
ALISTabsContent.displayName = "ALISTabsContent";

/** Legacy export — kept for backward compat, no longer needed */
function ALISTabsActiveBar(_props: { activeValue: string; tabs: { value: string }[] }) {
  return null;
}

export { ALISTabs, ALISTabsList, ALISTabsTrigger, ALISTabsContent, ALISTabsActiveBar };
