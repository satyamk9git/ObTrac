"use client";

export default function DBConfigPage() {
  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-2">
          <h1 className="text-2xl font-bold text-gray-900">Database Config</h1>
          <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 bg-gray-100 text-gray-500 rounded">Coming Soon</span>
        </div>
        <p className="text-sm text-gray-500 mt-1">
          Connect Cortexa to your own PostgreSQL database via connection string. Schema is auto-migrated. SQLite remains the default if no Postgres is configured.
        </p>
      </div>

      {/* Preview card */}
      <div className="card max-w-3xl">
        <div className="flex items-start gap-4">
          <div className="w-12 h-12 bg-indigo-50 rounded-lg flex items-center justify-center shrink-0">
            <svg className="w-6 h-6 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4" />
            </svg>
          </div>
          <div className="flex-1">
            <h2 className="text-base font-semibold text-gray-900">Bring Your Own Database</h2>
            <p className="text-sm text-gray-600 mt-1">
              The next milestone (M3) will let you plug in your own PostgreSQL via the dashboard:
            </p>
            <ul className="mt-3 space-y-2 text-sm text-gray-600">
              <li className="flex gap-2">
                <span className="text-indigo-500">•</span>
                <span>Enter a connection string (encrypted at rest in <code>~/.obtrac/db_config.json</code>)</span>
              </li>
              <li className="flex gap-2">
                <span className="text-indigo-500">•</span>
                <span>Test the connection before saving</span>
              </li>
              <li className="flex gap-2">
                <span className="text-indigo-500">•</span>
                <span>Mark it as the primary DB → restart backend → schema auto-created in PostgreSQL</span>
              </li>
              <li className="flex gap-2">
                <span className="text-indigo-500">•</span>
                <span>Old SQLite is renamed to <code>obtrac.db.archived</code> — your data stays safe but the new DB starts fresh</span>
              </li>
              <li className="flex gap-2">
                <span className="text-indigo-500">•</span>
                <span>SQL Editor will be able to query both the active DB and any saved Postgres connection</span>
              </li>
            </ul>
          </div>
        </div>
      </div>

      {/* Currently active */}
      <div className="card max-w-3xl mt-4">
        <h3 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2">Currently Active</h3>
        <div className="flex items-center gap-3">
          <div className="w-2 h-2 rounded-full bg-green-500" />
          <span className="text-sm font-mono text-gray-700">SQLite</span>
          <span className="text-xs text-gray-500">— ~/.obtrac/backend/data/obtrac.db</span>
        </div>
      </div>
    </div>
  );
}
