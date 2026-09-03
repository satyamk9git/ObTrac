"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

const API = "/api/v1";

type Job = {
  id: string;
  trace_id: string;
  project: string;
  status: string;
  progress_message: string;
  metrics: string[];
  judge_llm_config_ids: string[];
  created_at: string | null;
};

export default function RunningEvalsBadge() {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [open, setOpen] = useState(false);

  const fetchJobs = () => {
    fetch(`${API}/evaluation/jobs?status=queued,running&limit=20`)
      .then((r) => r.json())
      .then((d) => setJobs(d.jobs || []))
      .catch(() => setJobs([]));
  };

  useEffect(() => {
    fetchJobs();
    const interval = setInterval(fetchJobs, 5000);
    return () => clearInterval(interval);
  }, []);

  const count = jobs.length;
  if (count === 0) return null;

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-50 border border-indigo-200 hover:bg-indigo-100 transition-colors"
        title={`${count} evaluation${count !== 1 ? "s" : ""} running`}
      >
        <svg className="animate-spin w-3.5 h-3.5 text-indigo-600" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
        </svg>
        <span className="text-xs font-semibold text-indigo-700">
          {count} eval{count !== 1 ? "s" : ""} running
        </span>
      </button>

      {open && (
        <>
          <div
            className="fixed inset-0 z-30"
            onClick={() => setOpen(false)}
          />
          <div className="absolute right-0 top-full mt-2 w-96 bg-white border border-gray-200 rounded-lg shadow-xl z-40 overflow-hidden">
            <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
              <p className="text-sm font-semibold text-gray-900">Running Evaluations</p>
              <p className="text-[11px] text-gray-500">Auto-refreshes every 5 seconds</p>
            </div>
            <div className="max-h-96 overflow-y-auto">
              {jobs.map((job) => {
                const isBulk = job.trace_id === "__bulk__";
                const content = (
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex-1 min-w-0">
                      <p className="text-xs font-mono text-gray-700 truncate">
                        {isBulk ? "Bulk eval (missing metrics)" : `${job.trace_id.slice(0, 12)}...`}
                      </p>
                      <p className="text-[11px] text-gray-500 mt-0.5">
                        {job.project} • {job.metrics.length} metric{job.metrics.length !== 1 ? "s" : ""}
                        {!isBulk && ` × ${job.judge_llm_config_ids.length} LLM${job.judge_llm_config_ids.length !== 1 ? "s" : ""}`}
                      </p>
                      <p className="text-[11px] text-indigo-600 mt-1 truncate">
                        {job.progress_message || job.status}
                      </p>
                    </div>
                    <span className={`text-[9px] font-bold uppercase px-1.5 py-0.5 rounded ${
                      job.status === "running"
                        ? "bg-indigo-100 text-indigo-700"
                        : "bg-gray-100 text-gray-500"
                    }`}>
                      {job.status}
                    </span>
                  </div>
                );
                if (isBulk) {
                  return (
                    <div key={job.id} className="block px-4 py-3 border-b border-gray-100">
                      {content}
                    </div>
                  );
                }
                return (
                  <Link
                    key={job.id}
                    href={`/traces/${job.trace_id}?project=${encodeURIComponent(job.project)}`}
                    onClick={() => setOpen(false)}
                    className="block px-4 py-3 border-b border-gray-100 hover:bg-gray-50 transition-colors"
                  >
                    {content}
                  </Link>
                );
              })}
            </div>
          </div>
        </>
      )}
    </div>
  );
}
