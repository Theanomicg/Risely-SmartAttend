import SectionCard from "./SectionCard";
import { buildProtectedAssetUrl } from "../api";

function StudentsList({ students }) {
  return (
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
                    src={buildProtectedAssetUrl(photo.url, "admin")}
                    alt={`${student.name} enrollment ${photo.original_filename}`}
                    className="h-24 w-full rounded-xl object-cover"
                  />
                ))}
              </div>
            )}
            {student.photos?.length === 0 && <p className="mt-2 text-sm text-slate-500">No enrollment photos available.</p>}
          </div>
        ))}
        {students.length === 0 && <p className="text-slate-500">No students loaded.</p>}
      </div>
    </SectionCard>
  );
}

function CamerasList({ cameras }) {
  return (
    <SectionCard title="Cameras">
      <div className="space-y-3">
        {cameras.map((camera) => (
          <div key={camera.class_id} className="rounded-2xl border border-slate-200 p-4">
            <p className="font-semibold">{camera.display_name}</p>
            <p className="text-sm text-slate-600">{camera.class_id}</p>
            <p className="text-sm text-slate-600 break-all">{camera.rtsp_url_masked}</p>
            <p className="text-sm text-slate-500">{camera.enabled ? "Enabled" : "Disabled"}</p>
          </div>
        ))}
        {cameras.length === 0 && <p className="text-slate-500">No cameras configured.</p>}
      </div>
    </SectionCard>
  );
}

export { StudentsList, CamerasList };
