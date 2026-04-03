import SectionCard from "./SectionCard";
import { formatDate, formatTime } from "../formatters";

function AttendanceLog({ attendanceSessions, loading }) {
  return (
    <SectionCard title="Attendance Log">
      <div className="overflow-x-auto">
        <table className="min-w-full border-separate border-spacing-y-2">
          <thead>
            <tr className="text-left text-sm uppercase tracking-[0.18em] text-slate-500">
              <th className="px-3 py-2">Student</th>
              <th className="px-3 py-2">Date</th>
              <th className="px-3 py-2">Check in</th>
              <th className="px-3 py-2">Check out</th>
              <th className="px-3 py-2">Status</th>
            </tr>
          </thead>
          <tbody>
            {attendanceSessions.map((session) => {
              const primaryTimestamp = session.checked_in_at ?? session.checked_out_at;
              const statusLabel = session.status === "checked_in" ? "Checked in" : "Checked out";
              const statusClasses =
                session.status === "checked_in"
                  ? "bg-emerald-100 text-emerald-800"
                  : "bg-slate-200 text-slate-700";

              return (
                <tr key={`${session.uid}-${session.checked_in_at ?? "none"}-${session.checked_out_at ?? "none"}`}>
                  <td className="rounded-l-2xl bg-slate-50 px-3 py-3">
                    <p className="font-semibold text-ink">{session.name}</p>
                    <p className="text-sm text-slate-600">{session.uid}</p>
                  </td>
                  <td className="bg-slate-50 px-3 py-3 text-sm text-slate-700">{formatDate(primaryTimestamp)}</td>
                  <td className="bg-slate-50 px-3 py-3 text-sm text-slate-700">{formatTime(session.checked_in_at)}</td>
                  <td className="bg-slate-50 px-3 py-3 text-sm text-slate-700">{formatTime(session.checked_out_at)}</td>
                  <td className="rounded-r-2xl bg-slate-50 px-3 py-3">
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em] ${statusClasses}`}>
                      {statusLabel}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {!loading && attendanceSessions.length === 0 && (
          <p className="px-3 py-4 text-slate-500">No attendance records yet for this class.</p>
        )}
      </div>
    </SectionCard>
  );
}

export default AttendanceLog;
