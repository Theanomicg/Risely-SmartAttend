import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api";
const DEFAULT_CLASS_ID = import.meta.env.VITE_CLASS_ID ?? import.meta.env.VITE_CLASSROOM_ID ?? "class-10-a";

function formatDateTime(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function formatDate(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit"
  }).format(date);
}

function formatTime(value) {
  if (!value) {
    return "-";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat(undefined, {
    hour: "2-digit",
    minute: "2-digit"
  }).format(date);
}

function SectionCard({ title, children, action }) {
  return (
    <section className="rounded-3xl border border-white/70 bg-white/70 p-6 shadow-[0_20px_60px_rgba(15,23,42,0.08)] backdrop-blur">
      <div className="mb-5 flex items-center justify-between gap-4">
        <h2 className="font-display text-2xl text-ink">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function App() {
  const [classId, setClassId] = useState(DEFAULT_CLASS_ID);
  const [activeStudents, setActiveStudents] = useState([]);
  const [attendanceSessions, setAttendanceSessions] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [students, setStudents] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [settings, setSettings] = useState({
    monitoring_interval_minutes: 5,
    absence_alert_threshold_minutes: 15
  });
  const [studentForm, setStudentForm] = useState({ uid: "", name: "", class_id: "", photos: [] });
  const [cameraForm, setCameraForm] = useState({ class_id: "", display_name: "", rtsp_url: "", enabled: true });
  const [studentStatus, setStudentStatus] = useState({ type: "", message: "" });
  const [cameraStatus, setCameraStatus] = useState({ type: "", message: "" });
  const [settingsStatus, setSettingsStatus] = useState({ type: "", message: "" });

  const fetchJson = async (path, options) => {
    let response;
    try {
      response = await fetch(`${API_BASE}${path}`, options);
    } catch (error) {
      throw new Error(
        "Failed to reach the backend. Check that the API is running and restart the dashboard dev server."
      );
    }
    if (!response.ok) {
      const text = await response.text();
      try {
        const payload = JSON.parse(text);
        throw new Error(payload.detail ?? text);
      } catch {
        throw new Error(text);
      }
    }
    return response.json();
  };

  const refreshAttendance = async () => {
    const [active, sessions, currentAlerts] = await Promise.all([
      fetchJson(`/active-students?class_id=${encodeURIComponent(classId)}`),
      fetchJson(`/attendance-sessions?class_id=${encodeURIComponent(classId)}&limit=50`),
      fetchJson(`/alerts?class_id=${encodeURIComponent(classId)}`)
    ]);
    setActiveStudents(active);
    setAttendanceSessions(sessions);
    setAlerts(currentAlerts);
  };

  const refreshAdmin = async () => {
    const [allStudents, allCameras, monitoringSettings] = await Promise.all([
      fetchJson("/admin/students"),
      fetchJson("/admin/cameras"),
      fetchJson("/admin/settings")
    ]);
    setStudents(allStudents);
    setCameras(allCameras);
    setSettings(monitoringSettings);
  };

  useEffect(() => {
    refreshAttendance();
    refreshAdmin();
    const pollId = window.setInterval(refreshAttendance, 15000);
    return () => window.clearInterval(pollId);
  }, [classId]);

  useEffect(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/alerts/${classId}`);
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "absence_alert") {
        setAlerts((current) => {
          const exists = current.some((item) => item.id === payload.id);
          return exists ? current : [payload, ...current];
        });
      }
    };
    const heartbeat = window.setInterval(() => {
      if (socket.readyState === WebSocket.OPEN) {
        socket.send("ping");
      }
    }, 10000);
    return () => {
      window.clearInterval(heartbeat);
      socket.close();
    };
  }, [classId]);

  const summary = useMemo(() => {
    return {
      checkedIn: activeStudents.length,
      unresolvedAlerts: alerts.filter((alert) => alert.status === "active").length
    };
  }, [activeStudents, alerts]);

  const acknowledgeAlert = async (id) => {
    await fetchJson(`/alerts/${id}/acknowledge`, { method: "POST" });
    setAlerts((current) => current.filter((alert) => alert.id !== id));
  };

  const dismissAlert = async (id) => {
    await fetchJson(`/alerts/${id}/dismiss`, { method: "POST" });
    setAlerts((current) => current.filter((alert) => alert.id !== id));
  };

  const submitStudent = async (event) => {
    event.preventDefault();
    setStudentStatus({ type: "", message: "" });

    if (!studentForm.uid || !studentForm.name || !studentForm.class_id) {
      setStudentStatus({ type: "error", message: "UID, full name, and class ID are required." });
      return;
    }

    const selectedPhotos = Array.from(studentForm.photos ?? []);
    if (selectedPhotos.length < 5) {
      setStudentStatus({ type: "error", message: "Upload at least 5 photos for embedding generation." });
      return;
    }

    const formData = new FormData();
    formData.append("uid", studentForm.uid);
    formData.append("name", studentForm.name);
    formData.append("class_id", studentForm.class_id);
    selectedPhotos.forEach((file) => formData.append("photos", file));

    try {
      await fetchJson("/admin/students", { method: "POST", body: formData });
      setStudentForm({ uid: "", name: "", class_id: "", photos: [] });
      setStudentStatus({ type: "success", message: "Student created successfully." });
      await refreshAdmin();
    } catch (error) {
      setStudentStatus({
        type: "error",
        message: error.message || "Student creation failed."
      });
    }
  };

  const submitCamera = async (event) => {
    event.preventDefault();
    setCameraStatus({ type: "", message: "" });
    try {
      await fetchJson("/admin/cameras", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(cameraForm)
      });
      setCameraForm({ class_id: "", display_name: "", rtsp_url: "", enabled: true });
      setCameraStatus({ type: "success", message: "Camera saved successfully." });
      await refreshAdmin();
    } catch (error) {
      setCameraStatus({ type: "error", message: error.message || "Camera save failed." });
    }
  };

  const saveSettings = async (event) => {
    event.preventDefault();
    setSettingsStatus({ type: "", message: "" });
    try {
      await fetchJson("/admin/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings)
      });
      setSettingsStatus({ type: "success", message: "Monitoring settings updated." });
    } catch (error) {
      setSettingsStatus({ type: "error", message: error.message || "Settings update failed." });
    }
  };

  return (
    <main className="mx-auto flex min-h-screen max-w-7xl flex-col gap-6 px-4 py-8 md:px-8">
      <header className="rounded-[2rem] bg-ink px-6 py-8 text-paper shadow-[0_24px_70px_rgba(15,23,42,0.28)]">
        <div className="flex flex-col gap-5 md:flex-row md:items-end md:justify-between">
          <div>
            <p className="mb-2 text-sm uppercase tracking-[0.3em] text-blue-200">SmartAttend</p>
            <h1 className="font-display text-4xl md:text-5xl">Attendance and classroom monitoring</h1>
          </div>
          <label className="flex max-w-xs flex-col gap-2 text-sm">
            <span className="text-blue-100">Teacher class view</span>
            <input
              className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-paper outline-none"
              value={classId}
              onChange={(event) => setClassId(event.target.value)}
            />
          </label>
        </div>
      </header>

      <section className="grid gap-4 md:grid-cols-2">
        <div className="rounded-3xl bg-mint p-6 text-white shadow-lg">
          <p className="text-sm uppercase tracking-[0.24em] text-emerald-100">Checked in</p>
          <p className="mt-3 font-display text-5xl">{summary.checkedIn}</p>
        </div>
        <div className="rounded-3xl bg-signal p-6 text-white shadow-lg">
          <p className="text-sm uppercase tracking-[0.24em] text-orange-100">Active alerts</p>
          <p className="mt-3 font-display text-5xl">{summary.unresolvedAlerts}</p>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <SectionCard title="Teacher Dashboard">
          <div className="grid gap-6 lg:grid-cols-2">
            <div>
              <h3 className="mb-3 text-lg font-semibold text-ink">Live checked-in students</h3>
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
                {activeStudents.length === 0 && <p className="text-slate-500">No active students for this class.</p>}
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
                        onClick={() => acknowledgeAlert(alert.id)}
                      >
                        Acknowledge
                      </button>
                      <button
                        className="rounded-xl border border-orange-300 px-4 py-2 text-sm font-medium text-orange-800"
                        onClick={() => dismissAlert(alert.id)}
                      >
                        Dismiss
                      </button>
                    </div>
                  </article>
                ))}
                {alerts.length === 0 && <p className="text-slate-500">No active alerts.</p>}
              </div>
            </div>
          </div>
        </SectionCard>

        <SectionCard title="Admin Panel">
          <div className="space-y-6">
            <form className="grid gap-3" onSubmit={submitStudent}>
              <h3 className="text-lg font-semibold">Register new student</h3>
              <input className="rounded-2xl border p-3" placeholder="UID" value={studentForm.uid} onChange={(e) => setStudentForm({ ...studentForm, uid: e.target.value })} />
              <input className="rounded-2xl border p-3" placeholder="Full name" value={studentForm.name} onChange={(e) => setStudentForm({ ...studentForm, name: e.target.value })} />
              <input className="rounded-2xl border p-3" placeholder="Class ID (example: Grade-10-A)" value={studentForm.class_id} onChange={(e) => setStudentForm({ ...studentForm, class_id: e.target.value })} />
              <input className="rounded-2xl border p-3" type="file" accept="image/*" multiple onChange={(e) => setStudentForm({ ...studentForm, photos: e.target.files })} />
              <p className="text-sm text-slate-500">Use class ID for the student's academic group or section, for example `Grade-10-A`, `CS-2026`, or `Classroom-B1`.</p>
              {studentStatus.message && (
                <p className={`text-sm ${studentStatus.type === "error" ? "text-red-600" : "text-emerald-700"}`}>
                  {studentStatus.message}
                </p>
              )}
              <button className="rounded-2xl bg-ink px-4 py-3 font-medium text-white" type="submit">Create student</button>
            </form>

            <form className="grid gap-3" onSubmit={submitCamera}>
              <h3 className="text-lg font-semibold">Configure camera</h3>
              <input className="rounded-2xl border p-3" placeholder="Class ID" value={cameraForm.class_id} onChange={(e) => setCameraForm({ ...cameraForm, class_id: e.target.value })} />
              <input className="rounded-2xl border p-3" placeholder="Display name" value={cameraForm.display_name} onChange={(e) => setCameraForm({ ...cameraForm, display_name: e.target.value })} />
              <input className="rounded-2xl border p-3" placeholder="RTSP URL" value={cameraForm.rtsp_url} onChange={(e) => setCameraForm({ ...cameraForm, rtsp_url: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={cameraForm.enabled} onChange={(e) => setCameraForm({ ...cameraForm, enabled: e.target.checked })} />
                Enabled
              </label>
              {cameraStatus.message && (
                <p className={`text-sm ${cameraStatus.type === "error" ? "text-red-600" : "text-emerald-700"}`}>
                  {cameraStatus.message}
                </p>
              )}
              <button className="rounded-2xl bg-mint px-4 py-3 font-medium text-white" type="submit">Save camera</button>
            </form>

            <form className="grid gap-3" onSubmit={saveSettings}>
              <h3 className="text-lg font-semibold">Monitoring settings</h3>
              <input
                className="rounded-2xl border p-3"
                type="number"
                min="1"
                value={settings.monitoring_interval_minutes}
                onChange={(e) => setSettings({ ...settings, monitoring_interval_minutes: Number(e.target.value) })}
              />
              <input
                className="rounded-2xl border p-3"
                type="number"
                min="1"
                value={settings.absence_alert_threshold_minutes}
                onChange={(e) => setSettings({ ...settings, absence_alert_threshold_minutes: Number(e.target.value) })}
              />
              {settingsStatus.message && (
                <p className={`text-sm ${settingsStatus.type === "error" ? "text-red-600" : "text-emerald-700"}`}>
                  {settingsStatus.message}
                </p>
              )}
              <button className="rounded-2xl bg-signal px-4 py-3 font-medium text-white" type="submit">Update settings</button>
            </form>
          </div>
        </SectionCard>
      </div>

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
          {attendanceSessions.length === 0 && (
            <p className="px-3 py-4 text-slate-500">No attendance records yet for this class.</p>
          )}
        </div>
      </SectionCard>

      <section className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Students">
          <div className="space-y-3">
            {students.map((student) => (
              <div key={student.uid} className="rounded-2xl border border-slate-200 p-4">
                <p className="font-semibold">{student.name}</p>
                <p className="text-sm text-slate-600">{student.uid} - {student.class_id}</p>
                <p className="text-sm text-slate-600">{student.embedding_count} embeddings</p>
                <p className="text-sm text-slate-600">{student.photo_count} saved enrollment photos</p>
                {student.photos?.length > 0 && (
                  <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {student.photos.map((photo) => (
                      <img
                        key={photo.id}
                        src={photo.url}
                        alt={`${student.name} enrollment ${photo.original_filename}`}
                        className="h-24 w-full rounded-xl object-cover"
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Cameras">
          <div className="space-y-3">
            {cameras.map((camera) => (
              <div key={camera.class_id} className="rounded-2xl border border-slate-200 p-4">
                <p className="font-semibold">{camera.display_name}</p>
                <p className="text-sm text-slate-600">{camera.class_id}</p>
                <p className="text-sm text-slate-600 break-all">{camera.rtsp_url}</p>
              </div>
            ))}
          </div>
        </SectionCard>
      </section>
    </main>
  );
}

export default App;
