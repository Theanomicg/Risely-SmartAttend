import { useEffect, useMemo, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
const DEFAULT_CLASSROOM = import.meta.env.VITE_CLASSROOM_ID ?? "classroom-a";

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
  const [classroomId, setClassroomId] = useState(DEFAULT_CLASSROOM);
  const [activeStudents, setActiveStudents] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [students, setStudents] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [settings, setSettings] = useState({
    monitoring_interval_minutes: 5,
    absence_alert_threshold_minutes: 15
  });
  const [studentForm, setStudentForm] = useState({ uid: "", name: "", class_id: "", photos: [] });
  const [cameraForm, setCameraForm] = useState({ classroom_id: "", display_name: "", rtsp_url: "", enabled: true });

  const fetchJson = async (path, options) => {
    const response = await fetch(`${API_BASE}${path}`, options);
    if (!response.ok) {
      throw new Error(await response.text());
    }
    return response.json();
  };

  const refreshAttendance = async () => {
    const [active, currentAlerts] = await Promise.all([
      fetchJson(`/active-students?classroom_id=${encodeURIComponent(classroomId)}`),
      fetchJson(`/alerts?classroom_id=${encodeURIComponent(classroomId)}`)
    ]);
    setActiveStudents(active);
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
  }, [classroomId]);

  useEffect(() => {
    const wsBase = API_BASE.replace(/^http/, "ws");
    const socket = new WebSocket(`${wsBase}/ws/alerts/${classroomId}`);
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
  }, [classroomId]);

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
    const formData = new FormData();
    formData.append("uid", studentForm.uid);
    formData.append("name", studentForm.name);
    formData.append("class_id", studentForm.class_id);
    Array.from(studentForm.photos).forEach((file) => formData.append("photos", file));
    await fetchJson("/admin/students", { method: "POST", body: formData });
    setStudentForm({ uid: "", name: "", class_id: "", photos: [] });
    await refreshAdmin();
  };

  const submitCamera = async (event) => {
    event.preventDefault();
    await fetchJson("/admin/cameras", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cameraForm)
    });
    setCameraForm({ classroom_id: "", display_name: "", rtsp_url: "", enabled: true });
    await refreshAdmin();
  };

  const saveSettings = async (event) => {
    event.preventDefault();
    await fetchJson("/admin/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(settings)
    });
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
            <span className="text-blue-100">Teacher classroom view</span>
            <input
              className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3 text-paper outline-none"
              value={classroomId}
              onChange={(event) => setClassroomId(event.target.value)}
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
                    <p className="text-sm text-slate-600">Last seen: {student.last_seen_at ?? "Not yet detected"}</p>
                  </article>
                ))}
                {activeStudents.length === 0 && <p className="text-slate-500">No active students for this classroom.</p>}
              </div>
            </div>

            <div>
              <h3 className="mb-3 text-lg font-semibold text-ink">Real-time absence alerts</h3>
              <div className="space-y-3">
                {alerts.map((alert) => (
                  <article key={alert.id} className="rounded-2xl border border-orange-200 bg-orange-50 p-4">
                    <p className="font-semibold text-orange-900">{alert.student_name}</p>
                    <p className="text-sm text-orange-800">Missing for {alert.duration_minutes} minutes</p>
                    <p className="text-sm text-orange-700">Last seen: {alert.last_seen_at ?? "No CCTV detection yet"}</p>
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
              <input className="rounded-2xl border p-3" placeholder="Class ID" value={studentForm.class_id} onChange={(e) => setStudentForm({ ...studentForm, class_id: e.target.value })} />
              <input className="rounded-2xl border p-3" type="file" accept="image/*" multiple onChange={(e) => setStudentForm({ ...studentForm, photos: e.target.files })} />
              <button className="rounded-2xl bg-ink px-4 py-3 font-medium text-white" type="submit">Create student</button>
            </form>

            <form className="grid gap-3" onSubmit={submitCamera}>
              <h3 className="text-lg font-semibold">Configure camera</h3>
              <input className="rounded-2xl border p-3" placeholder="Classroom ID" value={cameraForm.classroom_id} onChange={(e) => setCameraForm({ ...cameraForm, classroom_id: e.target.value })} />
              <input className="rounded-2xl border p-3" placeholder="Display name" value={cameraForm.display_name} onChange={(e) => setCameraForm({ ...cameraForm, display_name: e.target.value })} />
              <input className="rounded-2xl border p-3" placeholder="RTSP URL" value={cameraForm.rtsp_url} onChange={(e) => setCameraForm({ ...cameraForm, rtsp_url: e.target.value })} />
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" checked={cameraForm.enabled} onChange={(e) => setCameraForm({ ...cameraForm, enabled: e.target.checked })} />
                Enabled
              </label>
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
              <button className="rounded-2xl bg-signal px-4 py-3 font-medium text-white" type="submit">Update settings</button>
            </form>
          </div>
        </SectionCard>
      </div>

      <section className="grid gap-6 lg:grid-cols-2">
        <SectionCard title="Students">
          <div className="space-y-3">
            {students.map((student) => (
              <div key={student.uid} className="rounded-2xl border border-slate-200 p-4">
                <p className="font-semibold">{student.name}</p>
                <p className="text-sm text-slate-600">{student.uid} · {student.class_id}</p>
                <p className="text-sm text-slate-600">{student.embedding_count} embeddings</p>
              </div>
            ))}
          </div>
        </SectionCard>

        <SectionCard title="Cameras">
          <div className="space-y-3">
            {cameras.map((camera) => (
              <div key={camera.classroom_id} className="rounded-2xl border border-slate-200 p-4">
                <p className="font-semibold">{camera.display_name}</p>
                <p className="text-sm text-slate-600">{camera.classroom_id}</p>
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
