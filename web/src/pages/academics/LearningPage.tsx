/**
 * LearningPage — P40 In-house Learning Management
 * Route: /academics/learning
 *
 * Tab 1: Materials     — course materials library (faculty: create/publish; student: read)
 * Tab 2: Assignments   — assignment list with status (faculty: manage; student: submit)
 * Tab 3: My Work       — student submissions + grades
 * Tab 4: Generate (AI) — AI content generation panel (faculty only)
 */
import { useState, useEffect } from "react";
import { learningApi } from "@/services/learning";
import type {
  CourseMaterial,
  Assignment,
  AssignmentSubmission,
  MaterialType,
  GenerationType,
} from "@/services/learning";

// ── design tokens (matching OBEPage palette) ─────────────────
const C = {
  bg:      "#0E1020",
  card:    "#11131F",
  surface: "#1A1D2E",
  text:    "#C9D1E9",
  muted:   "#7B82A8",
  border:  "#1E2235",
  teal:    "#1D9E75",
  purple:  "#5D5FEF",
  amber:   "#EF9F27",
  red:     "#E24B4A",
  blue:    "#60A5FA",
};

function authHeader() {
  return { Authorization: `Bearer ${localStorage.getItem("token") ?? ""}` };
}

// ── helpers ──────────────────────────────────────────────────

function statusColor(status: string): string {
  const map: Record<string, string> = {
    PUBLISHED: C.teal,
    DRAFT: C.amber,
    CLOSED: C.muted,
    ARCHIVED: C.muted,
    SUBMITTED: C.blue,
    UNDER_REVIEW: C.purple,
    GRADED: C.teal,
    RETURNED: C.amber,
  };
  return map[status] ?? C.muted;
}

function Badge({ label }: { label: string }) {
  return (
    <span
      className="text-[9px] font-bold uppercase tracking-wide px-2 py-0.5 rounded"
      style={{
        background: `${statusColor(label)}22`,
        color: statusColor(label),
        border: `1px solid ${statusColor(label)}44`,
      }}
    >
      {label}
    </span>
  );
}

function Skeleton({ h = 12 }: { h?: number }) {
  return (
    <div
      className="rounded-xl animate-pulse"
      style={{ height: `${h}px`, background: C.surface }}
    />
  );
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div
      className="text-sm p-3 rounded-lg"
      style={{ background: `${C.red}18`, color: C.red, border: `1px solid ${C.red}33` }}
    >
      {msg}
    </div>
  );
}

// ── Course selector ──────────────────────────────────────────

interface CourseOption {
  id: string;
  code: string;
  name: string;
}

function useCourses() {
  const [courses, setCourses] = useState<CourseOption[]>([]);
  useEffect(() => {
    fetch(
      `${import.meta.env.VITE_API_URL || "http://localhost:8000/api/v1"}/academics/courses`,
      { headers: authHeader() as HeadersInit }
    )
      .then((r) => r.json())
      .then((d) => setCourses(Array.isArray(d) ? d : d.courses ?? []))
      .catch(() => {});
  }, []);
  return courses;
}

// ── Tab 1: Materials ─────────────────────────────────────────

function MaterialsTab({
  courseId,
  role,
}: {
  courseId: string;
  role: string;
}) {
  const [items, setItems] = useState<CourseMaterial[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isFaculty = role !== "STUDENT";

  useEffect(() => {
    if (!courseId) return;
    setLoading(true);
    learningApi
      .listMaterials(courseId)
      .then((r) => setItems(r.materials))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [courseId]);

  async function handlePublish(id: string) {
    try {
      const updated = await learningApi.publishMaterial(id);
      setItems((prev) => prev.map((m) => (m.id === id ? updated : m)));
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }

  if (!courseId)
    return (
      <p className="text-sm" style={{ color: C.muted }}>
        Select a course above.
      </p>
    );

  return (
    <div className="space-y-3">
      {error && <ErrorBanner msg={error} />}
      {loading ? (
        Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} h={52} />)
      ) : items.length === 0 ? (
        <p className="text-sm" style={{ color: C.muted }}>
          No materials yet for this course.
        </p>
      ) : (
        items.map((m) => (
          <div
            key={m.id}
            className="flex items-center justify-between rounded-xl px-4 py-3"
            style={{ background: C.surface, border: `1px solid ${C.border}` }}
          >
            <div className="flex flex-col gap-0.5">
              <span className="text-sm font-medium" style={{ color: C.text }}>
                {m.title}
              </span>
              <div className="flex gap-2 items-center">
                <Badge label={m.status} />
                <span className="text-[10px]" style={{ color: C.muted }}>
                  {m.material_type.replace("_", " ")}
                  {m.week_number ? ` · Week ${m.week_number}` : ""}
                  {m.is_ai_generated ? " · AI" : ""}
                </span>
              </div>
            </div>
            <div className="flex gap-2 items-center">
              {isFaculty && m.status === "DRAFT" && (
                <button
                  onClick={() => handlePublish(m.id)}
                  className="text-xs px-3 py-1 rounded-lg font-semibold transition-opacity hover:opacity-80"
                  style={{ background: C.teal, color: "#fff" }}
                >
                  Publish
                </button>
              )}
              {m.file_url && (
                <a
                  href={m.file_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-xs px-3 py-1 rounded-lg"
                  style={{ background: C.surface, color: C.blue, border: `1px solid ${C.border}` }}
                >
                  Download
                </a>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

// ── Tab 2: Assignments ───────────────────────────────────────

function AssignmentsTab({
  courseId,
  role,
  onSelectAssignment,
}: {
  courseId: string;
  role: string;
  onSelectAssignment: (a: Assignment) => void;
}) {
  const [items, setItems] = useState<Assignment[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isFaculty = role !== "STUDENT";

  useEffect(() => {
    if (!courseId) return;
    setLoading(true);
    learningApi
      .listAssignments(courseId)
      .then((r) => setItems(r.assignments))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [courseId]);

  async function handlePublish(id: string) {
    try {
      const updated = await learningApi.publishAssignment(id);
      setItems((prev) => prev.map((a) => (a.id === id ? updated : a)));
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }

  async function handleClose(id: string) {
    try {
      const updated = await learningApi.closeAssignment(id);
      setItems((prev) => prev.map((a) => (a.id === id ? updated : a)));
    } catch (e: unknown) {
      setError((e as Error).message);
    }
  }

  if (!courseId)
    return (
      <p className="text-sm" style={{ color: C.muted }}>
        Select a course above.
      </p>
    );

  return (
    <div className="space-y-3">
      {error && <ErrorBanner msg={error} />}
      {loading ? (
        Array.from({ length: 3 }).map((_, i) => <Skeleton key={i} h={64} />)
      ) : items.length === 0 ? (
        <p className="text-sm" style={{ color: C.muted }}>
          No assignments for this course.
        </p>
      ) : (
        items.map((a) => (
          <div
            key={a.id}
            className="rounded-xl px-4 py-3 cursor-pointer hover:opacity-90 transition-opacity"
            style={{ background: C.surface, border: `1px solid ${C.border}` }}
            onClick={() => onSelectAssignment(a)}
          >
            <div className="flex items-start justify-between">
              <div>
                <p className="text-sm font-medium" style={{ color: C.text }}>
                  {a.title}
                </p>
                <div className="flex gap-2 items-center mt-1">
                  <Badge label={a.status} />
                  <span className="text-[10px]" style={{ color: C.muted }}>
                    {a.max_marks} marks · Due {a.due_date?.slice(0, 10)}
                    {a.allow_late ? " (late OK)" : ""}
                    {a.is_ai_generated ? " · AI" : ""}
                  </span>
                </div>
              </div>
              {isFaculty && (
                <div className="flex gap-2">
                  {a.status === "DRAFT" && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handlePublish(a.id);
                      }}
                      className="text-xs px-3 py-1 rounded-lg font-semibold"
                      style={{ background: C.teal, color: "#fff" }}
                    >
                      Publish
                    </button>
                  )}
                  {a.status === "PUBLISHED" && (
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleClose(a.id);
                      }}
                      className="text-xs px-3 py-1 rounded-lg"
                      style={{ background: C.surface, color: C.amber, border: `1px solid ${C.amber}44` }}
                    >
                      Close
                    </button>
                  )}
                </div>
              )}
            </div>
          </div>
        ))
      )}
    </div>
  );
}

// ── Tab 3: My Work (submissions) ─────────────────────────────

function MyWorkTab({ assignmentId }: { assignmentId: string | null }) {
  const [sub, setSub] = useState<AssignmentSubmission | null>(null);
  const [text, setText] = useState("");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!assignmentId) return;
    setLoading(true);
    learningApi
      .getMySubmission(assignmentId)
      .then((s) => {
        setSub(s);
        setText(s.content_text ?? "");
      })
      .catch(() => setSub(null))
      .finally(() => setLoading(false));
  }, [assignmentId]);

  async function handleSave() {
    if (!assignmentId) return;
    setSaving(true);
    try {
      const updated = await learningApi.saveDraft(assignmentId, { content_text: text });
      setSub(updated);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function handleSubmit() {
    if (!assignmentId) return;
    setSaving(true);
    try {
      await handleSave();
      const updated = await learningApi.submitAssignment(assignmentId);
      setSub(updated);
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  if (!assignmentId)
    return (
      <p className="text-sm" style={{ color: C.muted }}>
        Click an assignment in the Assignments tab to open your submission.
      </p>
    );

  return (
    <div className="space-y-4">
      {error && <ErrorBanner msg={error} />}
      {loading ? (
        <Skeleton h={120} />
      ) : sub && ["GRADED", "RETURNED"].includes(sub.status) ? (
        <div
          className="rounded-xl p-4 space-y-2"
          style={{ background: C.surface, border: `1px solid ${C.border}` }}
        >
          <div className="flex items-center gap-3">
            <Badge label={sub.status} />
            {sub.marks_awarded !== undefined && (
              <span className="text-sm font-semibold" style={{ color: C.teal }}>
                {sub.effective_marks ?? sub.marks_awarded} marks
                {sub.late_deduction ? ` (−${sub.late_deduction} late)` : ""}
              </span>
            )}
          </div>
          {sub.feedback && (
            <p className="text-sm" style={{ color: C.text }}>
              <span style={{ color: C.muted }}>Feedback: </span>
              {sub.feedback}
            </p>
          )}
          {sub.content_text && (
            <pre
              className="text-xs whitespace-pre-wrap p-3 rounded-lg"
              style={{ background: C.bg, color: C.muted, border: `1px solid ${C.border}` }}
            >
              {sub.content_text}
            </pre>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          <div className="flex items-center gap-2">
            {sub && <Badge label={sub.status} />}
            <span className="text-xs" style={{ color: C.muted }}>
              {sub?.submitted_at
                ? `Submitted ${sub.submitted_at.slice(0, 16).replace("T", " ")}`
                : "Not yet submitted"}
              {sub?.is_late ? " · Late" : ""}
            </span>
          </div>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            disabled={sub?.status === "SUBMITTED" || sub?.status === "UNDER_REVIEW"}
            rows={10}
            placeholder="Write your answer here…"
            className="w-full rounded-xl p-3 text-sm resize-none focus:outline-none"
            style={{
              background: C.bg,
              color: C.text,
              border: `1px solid ${C.border}`,
            }}
          />
          {(!sub || sub.status === "DRAFT") && (
            <div className="flex gap-3">
              <button
                onClick={handleSave}
                disabled={saving}
                className="text-sm px-4 py-2 rounded-lg"
                style={{ background: C.surface, color: C.text, border: `1px solid ${C.border}` }}
              >
                {saving ? "Saving…" : "Save Draft"}
              </button>
              <button
                onClick={handleSubmit}
                disabled={saving || !text.trim()}
                className="text-sm px-4 py-2 rounded-lg font-semibold"
                style={{ background: C.teal, color: "#fff", opacity: !text.trim() ? 0.5 : 1 }}
              >
                {saving ? "Submitting…" : "Submit"}
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Tab 4: Generate (AI) ─────────────────────────────────────

const GENERATION_OPTIONS: { value: GenerationType; label: string; desc: string }[] = [
  { value: "lecture_notes",        label: "Lecture Notes",    desc: "Structured notes for one session" },
  { value: "quiz_questions",       label: "Quiz",             desc: "MCQ / short questions with CO tags" },
  { value: "assignment_questions", label: "Assignment",       desc: "Higher-order questions with rubric" },
  { value: "lesson_plan",          label: "Lesson Plan",      desc: "Week-level plan with Bloom's alignment" },
];

function GenerateTab({ courseId }: { courseId: string }) {
  const [type, setType] = useState<GenerationType>("lecture_notes");
  const [week, setWeek] = useState(1);
  const [autoPublish, setAutoPublish] = useState(false);
  const [dueDate, setDueDate] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{
    title: string;
    body?: string;
    confidence?: number | null;
    tier?: string | null;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  if (!courseId)
    return (
      <p className="text-sm" style={{ color: C.muted }}>
        Select a course to generate content.
      </p>
    );

  async function handleGenerate() {
    if (!courseId) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      if (type === "assignment_questions") {
        if (!dueDate) {
          setError("Due date is required for assignments.");
          return;
        }
        const r = await learningApi.generateAssignment(courseId, {
          due_date: dueDate,
          auto_publish: autoPublish,
        });
        setResult({
          title: r.assignment.title,
          body: r.assignment.description,
          confidence: r.ai_confidence,
        });
      } else {
        const r = await learningApi.generateMaterial(courseId, {
          generation_type: type,
          week_number: week,
          auto_publish: autoPublish,
        });
        setResult({
          title: r.material.title,
          body: r.material.content_body,
          confidence: r.ai_confidence,
          tier: r.ai_confidence_tier,
        });
      }
    } catch (e: unknown) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-5">
      {/* Generation type picker */}
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        {GENERATION_OPTIONS.map((opt) => (
          <button
            key={opt.value}
            onClick={() => setType(opt.value)}
            className="rounded-xl p-3 text-left transition-all"
            style={{
              background: type === opt.value ? `${C.purple}22` : C.surface,
              border: `1px solid ${type === opt.value ? C.purple : C.border}`,
            }}
          >
            <p
              className="text-xs font-semibold"
              style={{ color: type === opt.value ? C.purple : C.text }}
            >
              {opt.label}
            </p>
            <p className="text-[10px] mt-0.5" style={{ color: C.muted }}>
              {opt.desc}
            </p>
          </button>
        ))}
      </div>

      {/* Options row */}
      <div className="flex flex-wrap gap-4 items-center">
        {type !== "assignment_questions" && (
          <label className="flex items-center gap-2 text-xs" style={{ color: C.text }}>
            Week
            <input
              type="number"
              min={1}
              max={52}
              value={week}
              onChange={(e) => setWeek(parseInt(e.target.value) || 1)}
              className="w-16 rounded-lg px-2 py-1 text-xs"
              style={{ background: C.bg, color: C.text, border: `1px solid ${C.border}` }}
            />
          </label>
        )}
        {type === "assignment_questions" && (
          <label className="flex items-center gap-2 text-xs" style={{ color: C.text }}>
            Due date
            <input
              type="date"
              value={dueDate}
              onChange={(e) => setDueDate(e.target.value)}
              className="rounded-lg px-2 py-1 text-xs"
              style={{ background: C.bg, color: C.text, border: `1px solid ${C.border}` }}
            />
          </label>
        )}
        <label className="flex items-center gap-2 text-xs cursor-pointer" style={{ color: C.text }}>
          <input
            type="checkbox"
            checked={autoPublish}
            onChange={(e) => setAutoPublish(e.target.checked)}
            className="accent-purple-500"
          />
          Auto-publish after generation
        </label>
      </div>

      <button
        onClick={handleGenerate}
        disabled={loading}
        className="flex items-center gap-2 text-sm px-5 py-2.5 rounded-xl font-semibold transition-opacity hover:opacity-80"
        style={{ background: C.purple, color: "#fff", opacity: loading ? 0.6 : 1 }}
      >
        {loading ? (
          <>
            <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
            Generating…
          </>
        ) : (
          "Generate with AI"
        )}
      </button>

      {error && <ErrorBanner msg={error} />}

      {result && (
        <div
          className="rounded-xl p-4 space-y-3"
          style={{ background: C.surface, border: `1px solid ${C.border}` }}
        >
          <div className="flex items-center justify-between">
            <p className="text-sm font-semibold" style={{ color: C.text }}>
              {result.title}
            </p>
            {result.confidence != null && (
              <span className="text-[10px] px-2 py-0.5 rounded" style={{ background: C.teal + "22", color: C.teal }}>
                Confidence {Math.round(result.confidence * 100)}%
                {result.tier ? ` · ${result.tier}` : ""}
              </span>
            )}
          </div>
          {result.body && (
            <pre
              className="text-xs whitespace-pre-wrap"
              style={{ color: C.muted, maxHeight: "400px", overflowY: "auto" }}
            >
              {result.body}
            </pre>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Page ────────────────────────────────────────────────

const TABS = ["Materials", "Assignments", "My Work", "Generate (AI)"] as const;
type Tab = (typeof TABS)[number];

export function LearningPage() {
  const [tab, setTab] = useState<Tab>("Materials");
  const [courseId, setCourseId] = useState("");
  const [selectedAssignment, setSelectedAssignment] = useState<Assignment | null>(null);

  // Detect role from JWT (quick decode — no verify, display only)
  const [role, setRole] = useState("FACULTY");
  useEffect(() => {
    try {
      const token = localStorage.getItem("token");
      if (!token) return;
      const payload = JSON.parse(atob(token.split(".")[1]));
      setRole(payload.role ?? "FACULTY");
    } catch {
      // ignore
    }
  }, []);

  const courses = useCourses();
  const isFaculty = role !== "STUDENT";

  // Students don't need Generate tab
  const visibleTabs = isFaculty ? TABS : (["Materials", "Assignments", "My Work"] as const);

  return (
    <div
      className="min-h-screen p-6 space-y-6"
      style={{ background: C.bg, color: C.text, fontFamily: "Inter, sans-serif" }}
    >
      {/* Header */}
      <div>
        <h1 className="text-xl font-bold" style={{ color: C.text }}>
          Learning
        </h1>
        <p className="text-xs mt-0.5" style={{ color: C.muted }}>
          Course materials, assignments & AI content generation
        </p>
      </div>

      {/* Course selector */}
      <div className="flex flex-wrap gap-3 items-center">
        <label className="text-xs font-medium" style={{ color: C.muted }}>
          Course
        </label>
        <select
          value={courseId}
          onChange={(e) => {
            setCourseId(e.target.value);
            setSelectedAssignment(null);
          }}
          className="rounded-lg px-3 py-1.5 text-sm"
          style={{ background: C.surface, color: C.text, border: `1px solid ${C.border}` }}
        >
          <option value="">— select a course —</option>
          {courses.map((c) => (
            <option key={c.id} value={c.id}>
              {c.code} — {c.name}
            </option>
          ))}
        </select>
        {selectedAssignment && (
          <span className="text-xs" style={{ color: C.muted }}>
            · {selectedAssignment.title}
            <button
              className="ml-2 underline"
              style={{ color: C.blue }}
              onClick={() => setSelectedAssignment(null)}
            >
              clear
            </button>
          </span>
        )}
      </div>

      {/* Tab bar */}
      <div className="flex gap-1 rounded-xl p-1" style={{ background: C.surface }}>
        {visibleTabs.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t as Tab)}
            className="flex-1 text-xs font-semibold py-2 rounded-lg transition-all"
            style={{
              background: tab === t ? C.purple : "transparent",
              color: tab === t ? "#fff" : C.muted,
            }}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div
        className="rounded-2xl p-5"
        style={{ background: C.card, border: `1px solid ${C.border}` }}
      >
        {tab === "Materials" && (
          <MaterialsTab courseId={courseId} role={role} />
        )}
        {tab === "Assignments" && (
          <AssignmentsTab
            courseId={courseId}
            role={role}
            onSelectAssignment={(a) => {
              setSelectedAssignment(a);
              setTab("My Work");
            }}
          />
        )}
        {tab === "My Work" && (
          <MyWorkTab assignmentId={selectedAssignment?.id ?? null} />
        )}
        {tab === "Generate (AI)" && isFaculty && (
          <GenerateTab courseId={courseId} />
        )}
      </div>
    </div>
  );
}

export default LearningPage;
