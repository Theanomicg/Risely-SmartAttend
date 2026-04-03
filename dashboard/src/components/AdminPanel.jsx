import SectionCard from "./SectionCard";
import { formatDateTime } from "../formatters";

function StatusText({ status }) {
  if (!status?.message) {
    return null;
  }

  return <p className={`text-sm ${status.type === "error" ? "text-red-600" : "text-emerald-700"}`}>{status.message}</p>;
}

function CameraStatusCard({ cameraStatus }) {
  const tone =
    cameraStatus.status === "online"
      ? "text-emerald-700"
      : cameraStatus.status === "error"
        ? "text-rose-700"
        : "text-slate-600";

  return (
    <div className="rounded-2xl border border-slate-200 p-4">
      <div className="flex items-center justify-between gap-4">
        <div>
          <p className="font-semibold">{cameraStatus.display_name}</p>
          <p className="text-sm text-slate-600">{cameraStatus.class_id}</p>
        </div>
        <span className={`text-sm font-semibold uppercase tracking-[0.14em] ${tone}`}>{cameraStatus.status}</span>
      </div>
      <p className="mt-2 text-sm text-slate-600">
        Last checked: {cameraStatus.last_checked_at ? formatDateTime(cameraStatus.last_checked_at) : "Not yet checked"}
      </p>
      <p className="text-sm text-slate-600">
        Last success: {cameraStatus.last_success_at ? formatDateTime(cameraStatus.last_success_at) : "No successful frame yet"}
      </p>
      {cameraStatus.last_error ? <p className="mt-2 text-sm text-rose-700">{cameraStatus.last_error}</p> : null}
    </div>
  );
}

function AdminPanel({
  studentForm,
  setStudentForm,
  cameraForm,
  setCameraForm,
  settings,
  setSettings,
  studentStatus,
  cameraStatus,
  settingsStatus,
  onSubmitStudent,
  onSubmitCamera,
  onSaveSettings,
  cameraStatuses,
  loading
}) {
  return (
    <SectionCard title="Admin Panel">
      <div className="space-y-6">
        <form className="grid gap-3" onSubmit={onSubmitStudent}>
          <h3 className="text-lg font-semibold">Register new student</h3>
          <input className="rounded-2xl border p-3" placeholder="UID" value={studentForm.uid} onChange={(e) => setStudentForm({ ...studentForm, uid: e.target.value })} />
          <input className="rounded-2xl border p-3" placeholder="Full name" value={studentForm.name} onChange={(e) => setStudentForm({ ...studentForm, name: e.target.value })} />
          <input className="rounded-2xl border p-3" placeholder="Class ID (example: Grade-10-A)" value={studentForm.class_id} onChange={(e) => setStudentForm({ ...studentForm, class_id: e.target.value })} />
          <input className="rounded-2xl border p-3" type="file" accept="image/*" multiple onChange={(e) => setStudentForm({ ...studentForm, photos: e.target.files })} />
          <p className="text-sm text-slate-500">Use class ID for the student's academic group or section, for example `Grade-10-A`, `CS-2026`, or `Classroom-B1`.</p>
          <StatusText status={studentStatus} />
          <button className="rounded-2xl bg-ink px-4 py-3 font-medium text-white" type="submit">Create student</button>
        </form>

        <form className="grid gap-3" onSubmit={onSubmitCamera}>
          <h3 className="text-lg font-semibold">Configure camera</h3>
          <input className="rounded-2xl border p-3" placeholder="Class ID" value={cameraForm.class_id} onChange={(e) => setCameraForm({ ...cameraForm, class_id: e.target.value })} />
          <input className="rounded-2xl border p-3" placeholder="Display name" value={cameraForm.display_name} onChange={(e) => setCameraForm({ ...cameraForm, display_name: e.target.value })} />
          <input className="rounded-2xl border p-3" placeholder="RTSP URL" value={cameraForm.rtsp_url} onChange={(e) => setCameraForm({ ...cameraForm, rtsp_url: e.target.value })} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={cameraForm.enabled} onChange={(e) => setCameraForm({ ...cameraForm, enabled: e.target.checked })} />
            Enabled
          </label>
          <StatusText status={cameraStatus} />
          <button className="rounded-2xl bg-mint px-4 py-3 font-medium text-white" type="submit">Save camera</button>
        </form>

        <form className="grid gap-3" onSubmit={onSaveSettings}>
          <h3 className="text-lg font-semibold">Monitoring settings</h3>
          <label className="grid gap-2 text-sm text-slate-600">
            <span>Monitoring interval in minutes</span>
            <input
              className="rounded-2xl border p-3"
              type="number"
              min="1"
              value={settings.monitoring_interval_minutes}
              onChange={(e) => setSettings({ ...settings, monitoring_interval_minutes: Number(e.target.value) })}
            />
          </label>
          <label className="grid gap-2 text-sm text-slate-600">
            <span>Absence alert threshold in minutes</span>
            <input
              className="rounded-2xl border p-3"
              type="number"
              min="1"
              value={settings.absence_alert_threshold_minutes}
              onChange={(e) => setSettings({ ...settings, absence_alert_threshold_minutes: Number(e.target.value) })}
            />
          </label>
          <StatusText status={settingsStatus} />
          <button className="rounded-2xl bg-signal px-4 py-3 font-medium text-white" type="submit">Update settings</button>
        </form>

        <div className="grid gap-3">
          <div className="flex items-center justify-between gap-3">
            <h3 className="text-lg font-semibold">Camera health</h3>
            {loading ? <span className="text-sm text-slate-500">Refreshing...</span> : null}
          </div>
          {cameraStatuses.length === 0 ? (
            <p className="text-sm text-slate-500">No camera status available yet.</p>
          ) : (
            cameraStatuses.map((item) => <CameraStatusCard key={item.class_id} cameraStatus={item} />)
          )}
        </div>
      </div>
    </SectionCard>
  );
}

export default AdminPanel;
