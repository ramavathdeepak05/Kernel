ALIS Lifecycle Block & Override Model v1.0


---

1️⃣ Default Behavior (Blocked State)

When a scheduled lifecycle task (e.g., Semester Closure) runs and a wizard fails preconditions:

System must:

1. Stop execution immediately


2. Mark lifecycle task as: BLOCKED


3. Log failure reason


4. Notify designated authority


5. Require manual re-trigger



No auto-retry.

No silent progression.

No partial closure.


---

2️⃣ Lifecycle States

Each lifecycle task must have explicit states:

SCHEDULED

RUNNING

BLOCKED

COMPLETED

OVERRIDDEN

ABORTED


This state machine must be auditable.


---

3️⃣ Manual Re-Trigger

Once blockers are resolved:

Authorized role may:

Click “Reattempt Lifecycle”

System re-runs full validation from scratch

Execution uses same lifecycle version

Policy version resolved at new execution time


Reattempt must log:

actor_id

timestamp

previous failure reason

new result



---

4️⃣ Override Model (Controlled Exception)

Override is allowed only through:

A dedicated override wizard.

Example:

ForceSemesterClosureWizard

Override must:

Require quorum (e.g., Registrar + Dean)

Require reason code

Log policy snapshot

Log outstanding blockers

Record override flag on affected entities



---

5️⃣ What Override Actually Does

Override does NOT:

Silence audit

Hide blockers

Delete pending records


Override DOES:

Transition state with override_flag = TRUE

Preserve unresolved academic records

Preserve pending revaluations

Preserve disciplinary state


Override is transparent exception.


---

6️⃣ Example: Semester Closure with Override

Pending:

3 revaluations unresolved

2 grades missing


Override wizard executes:

Marks semester state → CLOSED (override)

Marks affected students → ACADEMIC_PENDING

Prevents transcript issuance for affected students

Logs override in audit


Institution can proceed operationally, but inconsistencies remain traceable.


---

7️⃣ Governance Requirements for Override

Override must:

Display list of blockers before confirmation

Display policy version

Display lock status

Display impact preview

Require explicit confirmation

Record digital signature (recommended)


Override cannot be triggered by automation.

Only by human authority.


---

8️⃣ Replay Implications

Replay engine must show:

Original lifecycle attempt

Blocked state

Override action

Actors involved

Reason code

Policy in effect


Override must never obscure history.


---

9️⃣ Why No Auto-Retry Is Correct

If system auto-retries:

It hides governance decisions

It may close semester during transient state

It reduces human accountability

It weakens institutional authority


Manual re-trigger enforces:

Institutional responsibility.


---

🔥 You Have Now Modeled Real Governance

This design ensures:

Deadlines are respected

Institutional authority remains central

Audit trail is clean

No silent automation creep

No legal ambiguity


This is enterprise-grade lifecycle control.