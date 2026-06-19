// Renders a legal document (/legal/:doc) — terms, privacy, refunds, contact. Public.

import { Link, useParams } from "react-router-dom";
import { LEGAL_BY_SLUG } from "../legal/content";

export default function Legal() {
  const { doc } = useParams();
  const d = doc ? LEGAL_BY_SLUG[doc] : undefined;

  if (!d) {
    return (
      <div className="legal-page">
        <h1>Not found</h1>
        <p className="muted">No such document. <Link to="/">Home</Link></p>
      </div>
    );
  }

  return (
    <div className="legal-page">
      <div className="legal-draft">
        ⚠ Draft template — not legal advice. Have counsel review and replace the [placeholders] before
        relying on this.
      </div>
      <h1>{d.title}</h1>
      <p className="muted small">Last updated: {d.updated}</p>
      {d.sections.map((s) => (
        <section key={s.heading}>
          <h3>{s.heading}</h3>
          {s.paras.map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </section>
      ))}
      <p className="muted small"><Link to="/">← Back</Link></p>
    </div>
  );
}
