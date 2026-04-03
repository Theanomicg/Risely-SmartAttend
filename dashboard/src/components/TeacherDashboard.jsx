import SectionCard from "./SectionCard";
import { formatDateTime } from "../formatters";

function TeacherDashboard({ activeStudents, alerts, onAcknowledge, onDismiss, loading }) {
  return (
    <SectionCard title="Teacher Dashboard">
      <div className="grid gap-6 lg:grid-cols-2">
        <div>
          <h3 className="mb-3 text-lg font-semibold text-ink">Live checked-in students</h3>
          {loading ? <p className="text-slate-500">Loading teacher data...</p> : null}
          <div className="space-y-3">
            {activeStudents.map((student) => (
              <article key={student.uid} className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="font-semibold">{student.name}</p>
                <p className="text-sm text-slate-600">UID: {student.uid}</p>
                <p className="text-sm text-slate-600">Class: {student.class_id}</p>
                <p className="text-sm text-slate-600">Checked in: {formatDateTime(student.checked_in_at)}</p>
                <p className="text-sm text-slate-600">
                  Last seen: {student.last_seen_at ? formatDateTime(student.last_seen_at) : "Not yet detected"}
                </p>
              </article>
            ))}
            {!loading && activeStudents.length === 0 && (
              <p className="text-slate-500">No active students for this class.</p>
            )}
          </div>
        </div>

        <div>
          <h3 className="mb-3 text-lg font-semibold text-ink">Real-time absence alerts</h3>
          <div className="space-y-3">
            {alerts.map((alert) => (
              <article key={alert.id} className="rounded-2xl border border-orange-200 bg-orange-50 p-4">
                <p className="font-semibold text-orange-900">{alert.student_name}</p>
                <p className="text-sm text-orange-800">Missing for {alert.duration_minutes} minutes</p>
                <p className="text-sm text-orange-700">
                  Last seen: {alert.last_seen_at ? formatDateTime(alert.last_seen_at) : "No CCTV detection yet"}
                </p>
                <div className="mt-3 flex gap-2">
                  <button
                    className="rounded-xl bg-orange-600 px-4 py-2 text-sm font-medium text-white"
                    onClick={() => onAcknowledge(alert.id)}
                    type="button"
                  >
                    Acknowledge
                  </button>
                  <button
                    className="rounded-xl border border-orange-300 px-4 py-2 text-sm font-medium text-orange-800"
                    onClick={() => onDismiss(alert.id)}
                    type="button"
                  >
                    Dismiss
                  </button>
                </div>
              </article>
            ))}
            {!loading && alerts.length === 0 && <p className="text-slate-500">No active alerts.</p>}
          </div>
        </div>
      </div>
    </SectionCard>
  );
}

export default TeacherDashboard;
