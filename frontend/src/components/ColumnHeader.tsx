"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

export type SortDir = "asc" | "desc" | null;

export type ColumnHeaderProps = {
  label: string;
  /** Distinct values currently in the column — shown as multi-select checkboxes */
  values?: (string | number)[];
  /** Currently selected filter values (subset of `values`); empty = "show all" */
  selected?: (string | number)[];
  /** Called when the user toggles checkboxes / clears the filter */
  onFilterChange?: (next: (string | number)[]) => void;
  /** Set to enable sorting controls */
  sortable?: boolean;
  /** Current sort state */
  sortDir?: SortDir;
  /** Called when the user clicks asc/desc/clear */
  onSortChange?: (dir: SortDir) => void;
  /** Show a date-range picker instead of value list */
  dateRange?: boolean;
  /** Date range values (ISO strings) */
  dateFrom?: string;
  dateTo?: string;
  onDateRangeChange?: (from: string, to: string) => void;
};

export default function ColumnHeader({
  label,
  values = [],
  selected = [],
  onFilterChange,
  sortable = false,
  sortDir = null,
  onSortChange,
  dateRange = false,
  dateFrom = "",
  dateTo = "",
  onDateRangeChange,
}: ColumnHeaderProps) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [mounted, setMounted] = useState(false);
  const [popoverPos, setPopoverPos] = useState<{ top: number; left: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const popoverRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setMounted(true); }, []);

  // Compute popover position whenever it opens (or window scrolls/resizes)
  useLayoutEffect(() => {
    if (!open || !triggerRef.current) {
      setPopoverPos(null);
      return;
    }
    const update = () => {
      if (!triggerRef.current) return;
      const rect = triggerRef.current.getBoundingClientRect();
      // Popover is 256px wide; flip horizontally if it would overflow the right edge
      const popoverWidth = 256;
      let left = rect.left;
      if (left + popoverWidth > window.innerWidth - 8) {
        left = Math.max(8, window.innerWidth - popoverWidth - 8);
      }
      setPopoverPos({ top: rect.bottom + 4, left });
    };
    update();
    window.addEventListener("scroll", update, true);
    window.addEventListener("resize", update);
    return () => {
      window.removeEventListener("scroll", update, true);
      window.removeEventListener("resize", update);
    };
  }, [open]);

  // Close on outside click — checks both the trigger and the portal popover
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        triggerRef.current && !triggerRef.current.contains(target) &&
        popoverRef.current && !popoverRef.current.contains(target)
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const filterable = !!onFilterChange || dateRange;
  const isFiltered = (selected && selected.length > 0) || (dateRange && (dateFrom || dateTo));
  const hasInteractiveControl = filterable || sortable;

  // Filter the value list by the search box
  const filteredValues = values.filter((v) =>
    String(v).toLowerCase().includes(search.toLowerCase())
  );

  // The state model:
  //   selected = []                       → "show everything" (Select All checkbox is ON)
  //   selected = [...some subset]         → filter is active (master shows indeterminate)
  //   selected = ["__NONE__"] sentinel    → "hide everything" (no rows match, master OFF)
  const NONE = "__NONE__";
  const isShowAll = selected.length === 0;
  const isShowNone = selected.length === 1 && selected[0] === NONE;
  const allChecked = isShowAll;

  const toggleValue = (v: string | number) => {
    if (!onFilterChange) return;
    // Coming from "show all" state — start with everything except the unchecked one
    if (isShowAll) {
      onFilterChange(values.filter((x) => x !== v));
      return;
    }
    // Coming from "show none" — start with just this one
    if (isShowNone) {
      onFilterChange([v]);
      return;
    }
    const next = selected.includes(v)
      ? selected.filter((x) => x !== v)
      : [...selected, v];
    // If after toggle we end up with everything, collapse back to show-all
    if (next.length === values.length) {
      onFilterChange([]);
    } else if (next.length === 0) {
      onFilterChange([NONE]);
    } else {
      onFilterChange(next);
    }
  };

  const toggleSelectAll = () => {
    if (!onFilterChange) return;
    // If currently showing all → switch to none. Otherwise → show all.
    if (isShowAll) {
      onFilterChange([NONE]);
    } else {
      onFilterChange([]);
    }
  };

  const clearFilter = () => {
    onFilterChange?.([]);
    if (dateRange) {
      onDateRangeChange?.("", "");
    }
  };

  const clearSort = () => onSortChange?.(null);

  const popoverContent = open && popoverPos && (
    <div
      ref={popoverRef}
      style={{ top: popoverPos.top, left: popoverPos.left, width: 256 }}
      className="fixed z-[9999] bg-white border border-gray-200 rounded-lg shadow-xl overflow-hidden"
    >
          {/* Sort controls */}
          {sortable && (
            <div className="border-b border-gray-100">
              <button
                onClick={() => { onSortChange?.("asc"); setOpen(false); }}
                className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-gray-50 ${
                  sortDir === "asc" ? "text-indigo-700 font-semibold bg-indigo-50" : "text-gray-700"
                }`}
              >
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M5 12l5-5 5 5H5z" />
                </svg>
                Sort Ascending
              </button>
              <button
                onClick={() => { onSortChange?.("desc"); setOpen(false); }}
                className={`w-full text-left px-3 py-2 text-xs flex items-center gap-2 hover:bg-gray-50 ${
                  sortDir === "desc" ? "text-indigo-700 font-semibold bg-indigo-50" : "text-gray-700"
                }`}
              >
                <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 20 20">
                  <path d="M15 8l-5 5-5-5h10z" />
                </svg>
                Sort Descending
              </button>
              {sortDir && (
                <button
                  onClick={() => { clearSort(); setOpen(false); }}
                  className="w-full text-left px-3 py-2 text-xs text-gray-500 hover:bg-gray-50"
                >
                  Clear sort
                </button>
              )}
            </div>
          )}

          {/* Date range picker */}
          {dateRange && (
            <div className="p-3 border-b border-gray-100 space-y-2">
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">From</label>
                <input
                  type="date"
                  value={dateFrom}
                  onChange={(e) => onDateRangeChange?.(e.target.value, dateTo)}
                  className="w-full text-xs border border-gray-300 rounded px-2 py-1.5"
                />
              </div>
              <div>
                <label className="block text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-1">To</label>
                <input
                  type="date"
                  value={dateTo}
                  onChange={(e) => onDateRangeChange?.(dateFrom, e.target.value)}
                  className="w-full text-xs border border-gray-300 rounded px-2 py-1.5"
                />
              </div>
              {(dateFrom || dateTo) && (
                <button
                  onClick={() => onDateRangeChange?.("", "")}
                  className="text-[11px] text-gray-500 hover:text-gray-700"
                >
                  Clear date range
                </button>
              )}
            </div>
          )}

          {/* Value filter */}
          {onFilterChange && values.length > 0 && (
            <div>
              <div className="p-2 border-b border-gray-100">
                <input
                  type="text"
                  placeholder="Search..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  className="w-full text-xs border border-gray-300 rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-indigo-500"
                />
              </div>
              <div className="max-h-56 overflow-y-auto p-1">
                <label className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded cursor-pointer border-b border-gray-100">
                  <input
                    type="checkbox"
                    checked={allChecked}
                    ref={(el) => {
                      if (el) el.indeterminate = !isShowAll && !isShowNone;
                    }}
                    onChange={toggleSelectAll}
                    className="cursor-pointer"
                  />
                  <span className="text-xs font-semibold text-gray-700">
                    {allChecked ? "(Unselect All)" : "(Select All)"}
                  </span>
                </label>
                {filteredValues.map((v) => {
                  const isOn = !isShowNone && (allChecked || selected.includes(v));
                  return (
                    <label
                      key={String(v)}
                      className="flex items-center gap-2 px-2 py-1 hover:bg-gray-50 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={isOn}
                        onChange={() => toggleValue(v)}
                        className="cursor-pointer"
                      />
                      <span className="text-xs text-gray-700 truncate">{String(v) || "(blank)"}</span>
                    </label>
                  );
                })}
                {filteredValues.length === 0 && (
                  <p className="text-xs text-gray-400 px-2 py-2">No matches</p>
                )}
              </div>
              {isFiltered && !dateRange && (
                <div className="border-t border-gray-100 p-2">
                  <button
                    onClick={() => { clearFilter(); }}
                    className="text-[11px] text-gray-500 hover:text-gray-700 w-full text-left"
                  >
                    Clear filter
                  </button>
                </div>
              )}
            </div>
          )}
    </div>
  );

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => hasInteractiveControl && setOpen(!open)}
        className={`flex items-center gap-1 group ${
          hasInteractiveControl ? "cursor-pointer hover:text-gray-900" : "cursor-default"
        } ${isFiltered || sortDir ? "text-indigo-700" : ""}`}
      >
        <span>{label}</span>
        {sortable && sortDir === "asc" && (
          <svg className="w-3 h-3 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
            <path d="M5 12l5-5 5 5H5z" />
          </svg>
        )}
        {sortable && sortDir === "desc" && (
          <svg className="w-3 h-3 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
            <path d="M15 8l-5 5-5-5h10z" />
          </svg>
        )}
        {isFiltered && (
          <svg className="w-3 h-3 text-indigo-600" fill="currentColor" viewBox="0 0 20 20">
            <path d="M3 4a1 1 0 011-1h12a1 1 0 011 1v2a1 1 0 01-.293.707L12 11.414V17a1 1 0 01-1.447.894l-2-1A1 1 0 018 16v-4.586L3.293 6.707A1 1 0 013 6V4z" />
          </svg>
        )}
        {hasInteractiveControl && !isFiltered && !sortDir && (
          <svg className="w-3 h-3 text-gray-300 group-hover:text-gray-500 transition-colors" fill="currentColor" viewBox="0 0 20 20">
            <path d="M5 8l5 5 5-5H5z" />
          </svg>
        )}
      </button>
      {mounted && popoverContent && createPortal(popoverContent, document.body)}
    </>
  );
}
