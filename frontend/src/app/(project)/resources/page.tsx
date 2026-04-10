"use client";

import { useEffect, useState } from "react";

const API = "http://localhost:8100/api/v1";

export default function ResourcesPage() {
  const [datasets, setDatasets] = useState<any[]>([]);
  const [records, setRecords] = useState<any[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");
  const [uploading, setUploading] = useState(false);
  const [uploadResult, setUploadResult] = useState<any>(null);

  const fetchDatasets = () => {
    fetch(`${API}/resources/ground-truth/datasets?project=test-rag-app`)
      .then((r) => r.json())
      .then((data) => setDatasets(data.datasets || []))
      .catch(() => setDatasets([]));
  };

  const fetchRecords = (dataset: string) => {
    const params = new URLSearchParams({ project: "default" });
    if (dataset) params.set("dataset_name", dataset);

    fetch(`${API}/resources/ground-truth?${params}`)
      .then((r) => r.json())
      .then((data) => setRecords(data.records || []))
      .catch(() => setRecords([]));
  };

  useEffect(() => {
    fetchDatasets();
  }, []);

  useEffect(() => {
    if (selectedDataset !== undefined) {
      fetchRecords(selectedDataset);
    }
  }, [selectedDataset]);

  const handleUpload = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setUploading(true);
    setUploadResult(null);

    const formData = new FormData(e.currentTarget);

    try {
      const res = await fetch(`${API}/resources/ground-truth/upload`, {
        method: "POST",
        body: formData,
      });
      const data = await res.json();
      setUploadResult(data);
      fetchDatasets();
    } catch (err) {
      setUploadResult({ status: "error", error: String(err) });
    } finally {
      setUploading(false);
    }
  };

  const handleDeleteDataset = async (name: string) => {
    await fetch(
      `${API}/resources/ground-truth/dataset/${encodeURIComponent(name)}?project=test-rag-app`,
      { method: "DELETE" }
    );
    fetchDatasets();
    setRecords([]);
  };

  return (
    <div>
      <h1 className="text-2xl font-bold text-gray-900 mb-6">Resources</h1>

      {/* Upload Section */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">
          Upload Ground Truth
        </h2>
        <p className="text-sm text-gray-500 mb-4">
          Upload a CSV or JSON file with columns: <code>question</code>,{" "}
          <code>ground_truth</code>, <code>context</code> (optional).
        </p>

        <form onSubmit={handleUpload} className="flex gap-4 items-end">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              File (CSV/JSON)
            </label>
            <input
              type="file"
              name="file"
              accept=".csv,.json"
              required
              className="text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Dataset Name
            </label>
            <input
              type="text"
              name="dataset_name"
              placeholder="e.g., qa-v1"
              className="text-sm border rounded-lg px-3 py-2"
            />
          </div>
          <input type="hidden" name="project" value="default" />
          <button
            type="submit"
            disabled={uploading}
            className="bg-primary-600 text-white px-4 py-2 rounded-lg text-sm hover:bg-primary-700 disabled:opacity-50"
          >
            {uploading ? "Uploading..." : "Upload"}
          </button>
        </form>

        {uploadResult && (
          <div
            className={`mt-4 p-3 rounded-lg text-sm ${
              uploadResult.status === "uploaded"
                ? "bg-green-50 text-green-800 border border-green-200"
                : "bg-red-50 text-red-800 border border-red-200"
            }`}
          >
            {uploadResult.status === "uploaded"
              ? `Uploaded ${uploadResult.records_created} records to "${uploadResult.dataset_name}"`
              : `Error: ${uploadResult.error || "Upload failed"}`}
          </div>
        )}
      </div>

      {/* Datasets List */}
      <div className="bg-white rounded-lg border p-6 mb-6">
        <h2 className="text-lg font-semibold text-gray-800 mb-4">Datasets</h2>
        {datasets.length === 0 ? (
          <p className="text-sm text-gray-500">
            No datasets uploaded yet. Upload a ground truth file above.
          </p>
        ) : (
          <div className="space-y-2">
            {datasets.map((ds) => (
              <div
                key={ds.name}
                className={`flex justify-between items-center p-3 rounded-lg border cursor-pointer transition-colors ${
                  selectedDataset === ds.name
                    ? "bg-primary-50 border-primary-300"
                    : "hover:bg-gray-50"
                }`}
                onClick={() => setSelectedDataset(ds.name)}
              >
                <div>
                  <span className="font-medium text-sm">{ds.name}</span>
                  <span className="text-xs text-gray-500 ml-2">
                    {ds.count} records
                  </span>
                </div>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteDataset(ds.name);
                  }}
                  className="text-xs text-red-600 hover:text-red-800"
                >
                  Delete
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Records Table */}
      {records.length > 0 && (
        <div className="bg-white rounded-lg border overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b">
            <h3 className="text-sm font-semibold text-gray-700">
              Ground Truth Records ({records.length})
            </h3>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 py-2 text-left text-gray-600 w-1/3">
                  Question
                </th>
                <th className="px-4 py-2 text-left text-gray-600 w-1/3">
                  Ground Truth
                </th>
                <th className="px-4 py-2 text-left text-gray-600 w-1/4">
                  Context
                </th>
                <th className="px-4 py-2 text-left text-gray-600">Added</th>
              </tr>
            </thead>
            <tbody>
              {records.map((r) => (
                <tr key={r.id} className="border-t">
                  <td className="px-4 py-2 text-gray-700">{r.question}</td>
                  <td className="px-4 py-2 text-gray-700">{r.ground_truth}</td>
                  <td className="px-4 py-2 text-gray-500 text-xs truncate max-w-[200px]">
                    {r.context || "-"}
                  </td>
                  <td className="px-4 py-2 text-gray-500 text-xs">
                    {r.created_at
                      ? new Date(r.created_at).toLocaleDateString()
                      : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
