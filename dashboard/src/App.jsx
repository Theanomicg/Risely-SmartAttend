import { useEffect, useMemo, useState } from "react";

import AdminPanel from "./components/AdminPanel";
import AttendanceLog from "./components/AttendanceLog";
import StatusBanner from "./components/StatusBanner";
import TeacherDashboard from "./components/TeacherDashboard";
import { CamerasList, StudentsList } from "./components/ResourceLists";
import {
  DEFAULT_CLASS_ID,
  buildAlertsWebSocketUrl,
  fetchJson,
  fetchPublicJson
} from "./api";

function App() {
  const [classId, setClassId] = useState(DEFAULT_CLASS_ID);
  const [activeStudents, setActiveStudents] = useState([]);
  const [attendanceSessions, setAttendanceSessions] = useState([]);
  const [alerts, setAlerts] = useState([]);
  const [students, setStudents] = useState([]);
  const [cameras, setCameras] = useState([]);
  const [cameraStatuses, setCameraStatuses] = useState([]);
  const [settings, setSettings] = useState({
    monitoring_interval_minutes: 5,
    absence_alert_threshold_minutes: 15
  });
  const [systemStatus, setSystemStatus] = useState({
    api_status: "unknown",
    auth_enabled: false
  });
  const [loading, setLoading] = useState({
    attendance: true,
    admin: true
  });
  const [teacherError, setTeacherError] = useState("");
  const [adminError, setAdminError] = useState("");
  const [studentForm, setStudentForm] = useState({ uid: "", name: "", class_id: "", photos: [] });
  const [cameraForm, setCameraForm] = useState({ class_id: "", display_name: "", rtsp_url: "", enabled: true });
  const [studentStatus, setStudentStatus] = useState({ type: "", message: "" });
  const [cameraStatus, setCameraStatus] = useState({ type: "", message: "" });
  const [settingsStatus, setSettingsStatus] = useState({ type: "", message: "" });
  const [deletingStudentUid, setDeletingStudentUid] = useState("");
  const effectiveClassId = useMemo(() => classId.trim() || DEFAULT_CLASS_ID, [classId]);

  const refreshSystemStatus = async () => {
    try {
      const status = await fetchPublicJson("/health");
      setSystemStatus(status);
    } catch {
      setSystemStatus({ api_status: "offline", auth_enabled: false });
    }
  };

  const refreshAttendance = async () => {
    setLoading((current) => ({ ...current, attendance: true }));
    try {
      const [active, sessions, currentAlerts] = await Promise.all([
        fetchJson(`/active-students?class_id=${encodeURIComponent(effectiveClassId)}`),
        fetchJson(`/attendance-sessions?class_id=${encodeURIComponent(effectiveClassId)}&limit=50`),
        fetchJson(`/alerts?class_id=${encodeURIComponent(effectiveClassId)}`)
      ]);
      setActiveStudents(active);
      setAttendanceSessions(sessions);
      setAlerts(currentAlerts);
      setTeacherError("");
    } catch (error) {
      setTeacherError(error.message || "Teacher data request failed.");
    } finally {
      setLoading((current) => ({ ...current, attendance: false }));
    }
  };

  const refreshAdmin = async () => {
    setLoading((current) => ({ ...current, admin: true }));
    try {
      const [allStudents, allCameras, monitoringSettings, statusItems] = await Promise.all([
        fetchJson("/admin/students", { role: "admin" }),
        fetchJson("/admin/cameras", { role: "admin" }),
        fetchJson("/admin/settings", { role: "admin" }),
        fetchJson("/admin/camera-status", { role: "admin" })
      ]);
      setStudents(allStudents);
      setCameras(allCameras);
      setSettings(monitoringSettings);
      setCameraStatuses(statusItems);
      setAdminError("");
    } catch (error) {
      setAdminError(error.message || "Admin data request failed.");
    } finally {
      setLoading((current) => ({ ...current, admin: false }));
    }
  };

  useEffect(() => {
    refreshSystemStatus();
  }, []);

  useEffect(() => {
    refreshAttendance();
    const attendancePollId = window.setInterval(refreshAttendance, 15000);
    return () => {
      window.clearInterval(attendancePollId);
    };
  }, [effectiveClassId]);

  useEffect(() => {
    refreshAdmin();
    const adminPollId = window.setInterval(refreshAdmin, 30000);
    return () => {
      window.clearInterval(adminPollId);
    };
  }, []);

  useEffect(() => {
    const socket = new WebSocket(buildAlertsWebSocketUrl(effectiveClassId));
    socket.onopen = () => {
      setTeacherError((current) => (current === "Alert websocket disconnected." ? "" : current));
    };
    socket.onmessage = (event) => {
      const payload = JSON.parse(event.data);
      if (payload.type === "absence_alert") {
        setAlerts((current) => {
          const exists = current.some((item) => item.id === payload.id);
          return exists ? current : [payload, ...current];
        });
        return;
      }
      if (payload.type === "alert_resolved") {
        setAlerts((current) => current.filter((item) => item.id !== payload.id));
      }
    };
    socket.onerror = () => {
      setTeacherError((current) => current || "Alert websocket disconnected.");
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
  }, [effectiveClassId]);

  const summary = useMemo(() => {
    return {
      checkedIn: activeStudents.length,
      unresolvedAlerts: alerts.filter((alert) => alert.status === "active").length
    };
  }, [activeStudents, alerts]);

  const acknowledgeAlert = async (id) => {
    try {
      await fetchJson(`/alerts/${id}/acknowledge`, { method: "POST" });
      setAlerts((current) => current.filter((alert) => alert.id !== id));
      setTeacherError("");
    } catch (error) {
      setTeacherError(error.message || "Failed to acknowledge alert.");
    }
  };

  const dismissAlert = async (id) => {
    try {
      await fetchJson(`/alerts/${id}/dismiss`, { method: "POST" });
      setAlerts((current) => current.filter((alert) => alert.id !== id));
      setTeacherError("");
    } catch (error) {
      setTeacherError(error.message || "Failed to dismiss alert.");
    }
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
      await fetchJson("/admin/students", { method: "POST", body: formData, role: "admin" });
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
        body: JSON.stringify(cameraForm),
        role: "admin"
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
        body: JSON.stringify(settings),
        role: "admin"
      });
      setSettingsStatus({ type: "success", message: "Monitoring settings updated." });
      await refreshAdmin();
    } catch (error) {
      setSettingsStatus({ type: "error", message: error.message || "Settings update failed." });
    }
  };

  const deleteStudent = async (student) => {
    const confirmed = window.confirm(
      `Delete ${student.name} (${student.uid})? This removes the student, enrollment photos, attendance history, detections, active sessions, and alerts.`
    );
    if (!confirmed) {
      return;
    }

    setDeletingStudentUid(student.uid);
    setStudentStatus({ type: "", message: "" });
    try {
      const result = await fetchJson(`/admin/students/${encodeURIComponent(student.uid)}`, {
        method: "DELETE",
        role: "admin"
      });
      setStudentStatus({ type: "success", message: result.message || "Student deleted successfully." });
      await Promise.all([refreshAdmin(), refreshAttendance()]);
    } catch (error) {
      setStudentStatus({ type: "error", message: error.message || "Student deletion failed." });
    } finally {
      setDeletingStudentUid("");
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

      <StatusBanner systemStatus={systemStatus} teacherError={teacherError} adminError={adminError} />

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
        <TeacherDashboard
          activeStudents={activeStudents}
          alerts={alerts}
          onAcknowledge={acknowledgeAlert}
          onDismiss={dismissAlert}
          loading={loading.attendance}
        />
        <AdminPanel
          studentForm={studentForm}
          setStudentForm={setStudentForm}
          cameraForm={cameraForm}
          setCameraForm={setCameraForm}
          settings={settings}
          setSettings={setSettings}
          studentStatus={studentStatus}
          cameraStatus={cameraStatus}
          settingsStatus={settingsStatus}
          onSubmitStudent={submitStudent}
          onSubmitCamera={submitCamera}
          onSaveSettings={saveSettings}
          cameraStatuses={cameraStatuses}
          loading={loading.admin}
        />
      </div>

      <AttendanceLog attendanceSessions={attendanceSessions} loading={loading.attendance} />

      <section className="grid gap-6 lg:grid-cols-2">
        <StudentsList
          students={students}
          onDeleteStudent={deleteStudent}
          deletingStudentUid={deletingStudentUid}
        />
        <CamerasList cameras={cameras} />
      </section>
    </main>
  );
}

export default App;
