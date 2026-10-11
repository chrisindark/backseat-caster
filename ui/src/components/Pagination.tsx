"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import React from "react";

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  itemsPerPage: number;
  onPageChange: (page: number) => void;
  onItemsPerPageChange: (limit: number) => void;
}

export const Pagination: React.FC<PaginationProps> = ({
  currentPage,
  totalPages,
  totalItems,
  itemsPerPage,
  onPageChange,
  onItemsPerPageChange,
}) => {
  if (totalItems === 0) return null;

  const startItem = (currentPage - 1) * itemsPerPage + 1;
  const endItem = Math.min(currentPage * itemsPerPage, totalItems);

  // Generate page numbers
  const pages: number[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (
      p === 1 ||
      p === totalPages ||
      (p >= currentPage - 1 && p <= currentPage + 1)
    ) {
      pages.push(p);
    }
  }

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 py-8 border-t border-white/5 text-sm text-slate-400">
      {/* Items range and per-page selector */}
      <div className="flex items-center gap-3">
        <span>
          Showing <span className="text-white font-medium">{startItem}</span> -{" "}
          <span className="text-white font-medium">{endItem}</span> of{" "}
          <span className="text-white font-medium">{totalItems}</span> videos
        </span>
        <div className="flex items-center gap-1.5 ml-2">
          <span className="text-xs">Per page:</span>
          <select
            value={itemsPerPage}
            onChange={(e) => onItemsPerPageChange(Number(e.target.value))}
            className="bg-slate-900 border border-white/10 rounded-md px-2 py-1 text-xs text-slate-200 focus:outline-none focus:border-rose-500"
          >
            <option value={10}>10</option>
            <option value={20}>20</option>
            <option value={30}>30</option>
            <option value={40}>40</option>
            <option value={50}>50</option>
          </select>
        </div>
      </div>

      {/* Page Navigation */}
      <div className="flex items-center gap-1.5">
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage <= 1}
          className="p-2 rounded-lg bg-slate-900 border border-white/10 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          title="Previous Page"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>

        {pages.map((p, idx) => {
          const isCurrent = p === currentPage;
          const showEllipsisBefore = idx > 0 && p - pages[idx - 1] > 1;

          return (
            <React.Fragment key={p}>
              {showEllipsisBefore && <span className="px-1 text-slate-600">...</span>}
              <button
                onClick={() => onPageChange(p)}
                className={`min-w-9 h-9 px-3 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  isCurrent
                    ? "bg-rose-600 text-white shadow-md shadow-rose-900/40"
                    : "bg-slate-900 border border-white/10 text-slate-300 hover:bg-slate-800"
                }`}
              >
                {p}
              </button>
            </React.Fragment>
          );
        })}

        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage >= totalPages}
          className="p-2 rounded-lg bg-slate-900 border border-white/10 text-slate-300 hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-colors cursor-pointer"
          title="Next Page"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
};
