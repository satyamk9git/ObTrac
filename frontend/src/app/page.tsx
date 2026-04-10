"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SearchBar from "@/components/SearchBar";

const API = "http://localhost:8100/api/v1";

export default function ProjectsPage() {
  const [projects, setProjects] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API}/traces/projects`)
      .then((r) => r.json())
      .then((d) => setProjects(d.projects || []))
      .catch(() => setProjects([]))
      .finally(() => setLoading(false));
  }, []);

  const totalTraces = projects.reduce((s, p) => s + p.count, 0);
  const totalCost = projects.reduce((s, p) => s + (p.total_cost_usd || 0), 0);

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-6xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center text-white font-bold">
              O
            </div>
            <div>
              <h1 className="text-lg font-bold text-gray-900 tracking-tight">ObTrac</h1>
              <p className="text-[11px] text-gray-400 -mt-0.5">RAG Observability & Evaluation</p>
            </div>
          </div>
          <SearchBar />
        </div>
      </div>

      <div className="max-w-6xl mx-auto px-6 py-8">
        {/* Stats Row */}
        <div className="grid grid-cols-3 gap-4 mb-8">
          <div className="card">
            <p className="text-xs text-gray-500 mb-1">Total Projects</p>
            <p className="text-3xl font-bold text-gray-900">{projects.length}</p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 mb-1">Total Traces</p>
            <p className="text-3xl font-bold text-gray-900">{totalTraces}</p>
          </div>
          <div className="card">
            <p className="text-xs text-gray-500 mb-1">Total Cost</p>
            <p className="text-3xl font-bold text-gray-900">${totalCost.toFixed(4)}</p>
          </div>
        </div>

        {/* Project Cards */}
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Your Projects</h2>

        {loading ? (
          <div className="flex items-center justify-center py-20">
            <svg className="animate-spin w-6 h-6 text-indigo-500" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
            </svg>
          </div>
        ) : projects.length === 0 ? (
          <div className="card text-center py-16">
            <div className="w-16 h-16 bg-gray-100 rounded-2xl flex items-center justify-center mx-auto mb-4">
              <svg className="w-8 h-8 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
              </svg>
            </div>
            <h3 className="text-lg font-semibold text-gray-700 mb-2">No projects yet</h3>
            <p className="text-sm text-gray-500 max-w-md mx-auto">
              Run your RAG or Agent pipeline with ObTrac decorators to create your first project.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-4">
            {projects.map((p) => {
              const successRate = p.count > 0 ? ((p.success / p.count) * 100) : 0;
              return (
                <Link
                  key={p.name}
                  href={`/dashboard?project=${encodeURIComponent(p.name)}`}
                  className="card group cursor-pointer hover:border-indigo-300 animate-fade-in"
                >
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="text-base font-semibold text-gray-900 group-hover:text-indigo-600 transition-colors">
                        {p.name}
                      </h3>
                      <p className="text-xs text-gray-400 mt-0.5">
                        Last activity: {p.last_activity ? new Date(p.last_activity).toLocaleString() : "—"}
                      </p>
                    </div>
                    <svg className="w-5 h-5 text-gray-300 group-hover:text-indigo-500 transition-colors" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </div>

                  <div className="grid grid-cols-4 gap-3">
                    <div>
                      <p className="text-[10px] text-gray-400 uppercase">Traces</p>
                      <p className="text-lg font-bold text-gray-900">{p.count}</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-gray-400 uppercase">Success</p>
                      <p className={`text-lg font-bold ${successRate >= 90 ? "text-green-600" : successRate >= 70 ? "text-yellow-600" : "text-red-600"}`}>
                        {successRate.toFixed(0)}%
                      </p>
                    </div>
                    <div>
                      <p className="text-[10px] text-gray-400 uppercase">Avg Latency</p>
                      <p className="text-lg font-bold text-gray-900">{p.avg_latency_ms.toFixed(0)}ms</p>
                    </div>
                    <div>
                      <p className="text-[10px] text-gray-400 uppercase">Cost</p>
                      <p className="text-lg font-bold text-gray-900">${p.total_cost_usd.toFixed(4)}</p>
                    </div>
                  </div>

                  {/* Mini success bar */}
                  <div className="mt-3 w-full bg-gray-100 rounded-full h-1.5">
                    <div
                      className="h-1.5 rounded-full bg-gradient-to-r from-green-500 to-emerald-400 transition-all"
                      style={{ width: `${successRate}%` }}
                    />
                  </div>
                </Link>
              );
            })}
          </div>
        )}

        {/* Quick Links */}
        <div className="mt-8 grid grid-cols-2 gap-4">
          <Link href="/llm-config" className="card group hover:border-indigo-300">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-indigo-50 rounded-lg flex items-center justify-center">
                <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.066 2.573c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.573 1.066c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.066-2.573c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900 group-hover:text-indigo-600">LLM Configuration</p>
                <p className="text-xs text-gray-500">Manage LLM providers and keys</p>
              </div>
            </div>
          </Link>
          <Link href="/resources" className="card group hover:border-purple-300">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 bg-purple-50 rounded-lg flex items-center justify-center">
                <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
                </svg>
              </div>
              <div>
                <p className="text-sm font-medium text-gray-900 group-hover:text-purple-600">Resources</p>
                <p className="text-xs text-gray-500">Upload ground truth datasets</p>
              </div>
            </div>
          </Link>
        </div>
      </div>
    </div>
  );
}
