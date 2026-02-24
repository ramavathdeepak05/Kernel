ALIS Module-Scoped AI Agent Model v1.0

(Contained | Non-Reusable | Authority-Bound)


---

1️⃣ Core Principle

Each module owns its AI agents.

AI agents may not be shared across modules.

AI agents may not be invoked by another module.

AI agents may not cross module boundaries directly.

Automation may orchestrate modules,
but AI remains locally scoped.


---

2️⃣ Structural Model

Instead of:

GlobalAgentRegistry
    ↳ Used by all modules

You will have:

Admissions/
    agents/
        doc_verifier.py
        lead_scorer.py

Examinations/
    agents/
        script_grader.py
        question_paper_generator.py

Finance/
    agents/
        risk_scoring.py

Each module maintains:

Its own AgentRegistry

Its own prompt versions

Its own invocation rules

Its own confidence thresholds (policy-bound)



---

3️⃣ Why This Is Safe

This enforces:

Strong domain isolation

Reduced accidental authority creep

Reduced cross-context confusion

Clear audit segmentation

Clear debugging boundaries


Admissions AI cannot influence Exams AI logic.

Finance AI cannot accidentally score scholarship in Academics.


---

4️⃣ Invocation Boundary Rules

AI inside a module may:

Be triggered by automation

Be triggered by wizard

Be triggered by schedule


AI may not:

Trigger AI in another module

Modify automation config

Modify policy

Modify registry

Call cross-module DB directly


All cross-module interaction must go through:

Wizard → Core → Event Bus

Never AI → AI.


---

5️⃣ Versioning Model

Each module must maintain:

{
  "agent_id": "exam_script_grader_v2",
  "module": "Examinations",
  "model_version": "llama3.1_8b_v1",
  "prompt_version": "v3",
  "invocation_class": "EVALUATIVE",
  "authorization_policy": "exam_controller_required"
}

Agents are versioned independently per module.

Upgrading Exam AI does not affect Admissions AI.


---

6️⃣ Authorization Model

Even within module:

AI may require human authorization before invocation

Authorization rules are module-scoped

Authorization is version-bound


Example:

Exams → grading AI requires:

ExamController approval


Admissions → document verification may not.

Authorization cannot be auto-bypassed.


---

7️⃣ Automation Interaction

Automation may trigger module AI only if:

Authorization satisfied

Policy satisfied

Lock check passed


Automation may not:

Trigger AI in sequence across modules

Chain AI → AI → AI

Dynamically select agents


Max AI invocation per automation step = 1 (recommended).


---

8️⃣ Audit Isolation

Audit logs must record:

module

agent_id

agent_version

invocation_class

authorization_id

automation_version

policy_version

logic_version


Module-level separation simplifies dispute analysis.


---

9️⃣ Drift Containment

Drift in one module’s AI:

Does not propagate to others.

Example:

If script grader drifts, Admissions document verifier unaffected.

Containment is powerful.


---

🔟 Trade-Off You Accept

You sacrifice:

Agent reuse

Cross-module AI intelligence

Centralized AI analytics


But you gain:

Stability

Isolation

Governance clarity

Lower complexity

Easier certification


For a first institutional OS deployment, this is wise.


---

🧠 Important Structural Consequence

Because you chose module-scoped agents:

You do NOT need:

Global Agent Registry

Instead, you need:

Module Agent Registry per module.

Cleaner.

Safer.