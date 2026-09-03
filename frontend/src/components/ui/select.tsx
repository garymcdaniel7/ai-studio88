import * as React from "react";
import { Select as SelectPrimitive } from "@base-ui/react/select";
import { cn } from "@/lib/utils";

/**
 * Shared Select component (Base UI powered).
 *
 * Replaces the 55+ copy-pasted native `<select>` elements across the app with
 * one consistent, accessible, styled primitive. Supports all Base UI Select
 * features: value/label groups, disabled items, portals.
 *
 * Usage:
 *   <Select value={x} onValueChange={setX} placeholder="Pick one">
 *     <SelectItem value="a">Option A</SelectItem>
 *     <SelectItem value="b">Option B</SelectItem>
 *   </Select>
 */
function SelectRoot({
  className,
  placeholder,
  children,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Root> & {
  className?: string;
  placeholder?: React.ReactNode;
}) {
  return (
    <SelectPrimitive.Root {...props}>
      <SelectPrimitive.Trigger
        className={cn(
          "flex h-9 w-full items-center justify-between gap-2 rounded-lg border border-white/[0.08] bg-white/[0.03] px-3 py-1.5 text-sm text-white outline-none transition-colors",
          "hover:border-white/[0.15] focus-visible:border-white/[0.25] focus-visible:ring-2 focus-visible:ring-white/20",
          "disabled:pointer-events-none disabled:opacity-50",
          "data-[popup-open]:border-white/[0.25] data-[popup-open]:ring-2 data-[popup-open]:ring-white/20",
          className,
        )}
      >
        <SelectPrimitive.Value
          placeholder={placeholder}
          className="data-[placeholder]:text-white/40"
        />
        <SelectPrimitive.Icon className="shrink-0 text-white/50">
          <svg
            xmlns="http://www.w3.org/2000/svg"
            viewBox="0 0 20 20"
            fill="currentColor"
            className="size-4"
            aria-hidden
          >
            <path
              fillRule="evenodd"
              d="M5.23 7.21a.75.75 0 0 1 1.06.02L10 11.168l3.71-3.938a.75.75 0 1 1 1.08 1.04l-4.25 4.5a.75.75 0 0 1-1.08 0l-4.25-4.5a.75.75 0 0 1 .02-1.06Z"
              clipRule="evenodd"
            />
          </svg>
        </SelectPrimitive.Icon>
      </SelectPrimitive.Trigger>
      <SelectPrimitive.Portal>
        <SelectPrimitive.Positioner sideOffset={4} align="start">
          <SelectPrimitive.Popup className="z-50 max-h-[300px] min-w-[var(--anchor-width)] overflow-auto rounded-lg border border-white/[0.1] bg-[#111] p-1 shadow-2xl">
            <SelectPrimitive.List className="flex flex-col gap-0.5">
              {children}
            </SelectPrimitive.List>
          </SelectPrimitive.Popup>
        </SelectPrimitive.Positioner>
      </SelectPrimitive.Portal>
    </SelectPrimitive.Root>
  );
}

function SelectItem({
  className,
  children,
  ...props
}: React.ComponentProps<typeof SelectPrimitive.Item>) {
  return (
    <SelectPrimitive.Item
      className={cn(
        "flex cursor-pointer items-center justify-between rounded-md px-2.5 py-1.5 text-sm text-white/80 outline-none transition-colors",
        "hover:bg-white/[0.08] hover:text-white",
        "data-[selected]:bg-white/[0.12] data-[selected]:text-white",
        "data-[highlighted]:bg-white/[0.1] data-[highlighted]:text-white",
        className,
      )}
      {...props}
    >
      <SelectPrimitive.ItemText>{children}</SelectPrimitive.ItemText>
      <SelectPrimitive.ItemIndicator className="text-white/90">
        <svg
          xmlns="http://www.w3.org/2000/svg"
          viewBox="0 0 20 20"
          fill="currentColor"
          className="size-4"
          aria-hidden
        >
          <path
            fillRule="evenodd"
            d="M16.704 4.153a.75.75 0 0 1 .143 1.052l-8 10.5a.75.75 0 0 1-1.127.075l-4.5-4.5a.75.75 0 0 1 1.06-1.06l3.894 3.893 7.48-9.817a.75.75 0 0 1 1.05-.143Z"
            clipRule="evenodd"
          />
        </svg>
      </SelectPrimitive.ItemIndicator>
    </SelectPrimitive.Item>
  );
}

const SelectGroup = SelectPrimitive.Group;
const SelectGroupLabel = SelectPrimitive.GroupLabel;

export { SelectRoot as Select, SelectItem, SelectGroup, SelectGroupLabel };
