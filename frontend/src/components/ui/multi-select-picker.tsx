"use client";

import { useState } from "react";
import { ChevronsUpDown, X } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Command,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

export type PickerOption = {
  value: string;
  label: string;
  group?: string;
  badge?: string;
  description?: string;
};

// Fixed priority so related items (e.g. the same metric from different
// evaluation frameworks) land under separate, ordered, labeled headings
// instead of registry/array insertion order.
const GROUP_ORDER = ["ragas", "deepeval", "arize", "mlflow", "custom"];

type MultiSelectPickerProps = {
  options: PickerOption[];
  selected: string[];
  onChange: (next: string[]) => void;
  placeholder?: string;
  searchPlaceholder?: string;
  groupLabels?: Record<string, string>;
  emptyText?: string;
  triggerClassName?: string;
};

const VISIBLE_CHIP_CAP = 5;

/**
 * Searchable, grouped multi-select — replaces the flat `flex flex-wrap`
 * pill-row pattern that broke down once there were enough options to wrap
 * across several messy rows with no way to tell same-named items apart.
 */
export default function MultiSelectPicker({
  options,
  selected,
  onChange,
  placeholder = "Select...",
  searchPlaceholder = "Search...",
  groupLabels = {},
  emptyText = "No results found.",
  triggerClassName,
}: MultiSelectPickerProps) {
  const [open, setOpen] = useState(false);

  const toggle = (value: string) => {
    onChange(selected.includes(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };

  const groups = new Map<string, PickerOption[]>();
  for (const opt of options) {
    const key = opt.group || "";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key)!.push(opt);
  }
  const orderedGroupKeys = [
    ...GROUP_ORDER.filter((g) => groups.has(g)),
    ...Array.from(groups.keys()).filter((g) => !GROUP_ORDER.includes(g)),
  ];

  const selectedOptions = options.filter((o) => selected.includes(o.value));

  return (
    <div className="space-y-2">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <Button
            type="button"
            variant="outline"
            role="combobox"
            aria-expanded={open}
            className={cn("w-full justify-between font-normal", triggerClassName)}
          >
            <span className={selected.length ? "text-foreground" : "text-muted-foreground"}>
              {selected.length === 0 ? placeholder : `${selected.length} selected`}
            </span>
            <ChevronsUpDown className="ml-2 h-4 w-4 shrink-0 opacity-50" />
          </Button>
        </PopoverTrigger>
        <PopoverContent className="w-[--radix-popover-trigger-width] p-0" align="start">
          <Command>
            <CommandInput placeholder={searchPlaceholder} />
            <CommandList>
              <CommandEmpty>{emptyText}</CommandEmpty>
              {orderedGroupKeys.map((groupKey) => (
                <CommandGroup key={groupKey || "_ungrouped"} heading={groupLabels[groupKey] || groupKey || undefined}>
                  {groups.get(groupKey)!.map((opt) => {
                    const isSelected = selected.includes(opt.value);
                    return (
                      <CommandItem
                        key={opt.value}
                        value={`${opt.label} ${opt.value}`}
                        onSelect={() => toggle(opt.value)}
                        className="cursor-pointer gap-2"
                      >
                        <Checkbox checked={isSelected} className="shrink-0" />
                        <div className="flex-1 min-w-0 flex items-baseline gap-1.5">
                          <span className="truncate">{opt.label}</span>
                          {opt.description && (
                            <span className="text-xs text-muted-foreground truncate">{opt.description}</span>
                          )}
                        </div>
                        {opt.badge && (
                          <Badge variant="outline" className="ml-auto shrink-0 text-[10px]">
                            {opt.badge}
                          </Badge>
                        )}
                      </CommandItem>
                    );
                  })}
                </CommandGroup>
              ))}
            </CommandList>
          </Command>
        </PopoverContent>
      </Popover>

      {selectedOptions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedOptions.slice(0, VISIBLE_CHIP_CAP).map((opt) => (
            <Badge key={opt.value} variant="secondary" className="gap-1 pr-1 font-normal">
              {opt.label}
              <button
                type="button"
                onClick={() => toggle(opt.value)}
                className="ml-0.5 rounded-full hover:bg-foreground/10 p-0.5"
                aria-label={`Remove ${opt.label}`}
              >
                <X className="h-3 w-3" />
              </button>
            </Badge>
          ))}
          {selectedOptions.length > VISIBLE_CHIP_CAP && (
            <Badge variant="secondary" className="font-normal">
              +{selectedOptions.length - VISIBLE_CHIP_CAP} more
            </Badge>
          )}
        </div>
      )}
    </div>
  );
}
