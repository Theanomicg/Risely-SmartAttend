function StatusPill({ label, tone = "slate" }) {
  const tones = {
    green: "bg-emerald-100 text-emerald-800",
    amber: "bg-amber-100 text-amber-800",
    red: "bg-rose-100 text-rose-800",
    slate: "bg-slate-100 text-slate-700"
  };

  return (
    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${tones[tone]}`}>
      {label}
    </span>
  );
}

function StatusBanner({ systemStatus, teacherError, adminError }) {
  const apiTone = systemStatus.api_status === "ok" ? "green" : "red";
  const authTone = systemStatus.auth_enabled ? "amber" : "slate";

  return (
    <section className="grid gap-4 rounded-3xl border border-slate-200 bg-white/80 p-5 shadow-[0_16px_40px_rgba(15,23,42,0.06)] lg:grid-cols-[auto_auto_1fr]">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-600">API</span>
        <StatusPill label={systemStatus.api_status === "ok" ? "Online" : "Offline"} tone={apiTone} />
      </div>
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-slate-600">Auth</span>
        <StatusPill label={systemStatus.auth_enabled ? "Enabled" : "Disabled"} tone={authTone} />
      </div>
      <div className="grid gap-2 text-sm text-slate-600">
        {teacherError && <p className="text-rose-700">Teacher view: {teacherError}</p>}
        {adminError && <p className="text-rose-700">Admin view: {adminError}</p>}
        {!teacherError && !adminError && (
          <p>
            Teacher and admin requests are using the configured dashboard tokens when present. If auth is enabled,
            set `VITE_TEACHER_TOKEN` and `VITE_ADMIN_TOKEN`.
          </p>
        )}
      </div>
    </section>
  );
}

export default StatusBanner;
