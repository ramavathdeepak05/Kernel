graph TB
    %% ─── EXTERNAL CLIENTS ───
    subgraph Clients["External Clients"]
        Browser["Browser"]
        DesktopApp["Desktop App (Electron)"]
        Webhook["External Webhooks"]
    end

    %% ─── DESKTOP APP ───
    subgraph Desktop["desktop/ — Electron App (offline-first + Dexie local IndexedDB)"]
        ElectronMain["main/index.ts (Electron main process)"]
        subgraph DesktopRenderer["renderer/ (React)"]
            DLogin["LoginPage"]
            DCourse["CourseSelectorPage"]
            DSession["SessionPage"]
            DLiveRoster["LiveRoster"]
            DSessionCard["SessionCard"]
            DAuthStore["authStore.ts"]
        end
        ElectronMain --> DesktopRenderer
    end

    %% ─── CI/CD ───
    subgraph CICD["CI/CD — .github/workflows/ci.yml"]
        CILint["lint"] --> CIType["typecheck"] --> CITest["pytest (958 mocked)"] --> CITestInteg["pytest --real-db (16)"] --> CIBuild["build"]
    end

    %% ─── AGENT SKILLS (Claude Code) ───
    subgraph AgentSkills[".agents/skills/ — 23 Claude Code Skills"]
        SkillBackend["alis-backend-patterns\nalis-db-patterns\nalis-migration-writer"]
        SkillFrontend["alis-frontend-developer\nfrontend-design\nshadcn-ui-builder\nfullstack-developer"]
        SkillAI["alis-agent-builder\nalis-intent-layer\nalis-machine-learning\nalis-os\ncelery-orchestrator\nstitch-loop\nbrainstorming"]
        SkillGovernance["alis-audit-certifications\nalis-consent-management\nalis-data-encryption\nalis-data-governance\nalis-data-management\nalis-dynamic-rbac\nalis-governance-auditor\nalis-incident-response\nALIS-Claudecode"]
    end

    %% ─── FRONTEND (web/) ───
    subgraph Frontend["web/ — Vite 7 + React 19 + TypeScript + Tailwind v4"]
        subgraph FEShell["App Shell"]
            ALISShell["ALISShell"]
            AgentBottomSheet["AgentBottomSheet"]
            IconNav["IconNav"]
            PrimaryCanvas["PrimaryCanvas"]
        end

        subgraph FEPages["Pages (22 dirs)"]
            PAuth["auth/ (Login, MFA)"]
            PDash["dashboard/ (role-aware → 6 views)"]
            PAdmissions["admissions/ (portal + staff)"]
            PAcademics["academics/"]
            PExams["examinations/"]
            PFinance["finance/"]
            PHR["hr/"]
            PStudent["student-services/"]
            PAlumni["alumni/"]
            PComms["communications/"]
            PReports["reports/"]
            PSettings["settings/ (Roles, DLT)"]
            PWorkflows["workflows/"]
            PProcess["process-engine/"]
            POthers["phd/ regulatory/ convocation/ consent/ attendance/ portal/ admin/"]
        end

        subgraph FEViews["Role Dashboards (views/)"]
            VStudent["StudentDashboard"]
            VFaculty["FacultyDashboard"]
            VHOD["HODDashboard"]
            VRegistrar["RegistrarDashboard"]
            VFinance["FinanceDashboard"]
            VExamCtrl["ExamControllerDashboard"]
        end

        subgraph FELib["Lib & State"]
            ALISApi["alis-api.ts (typed API client)"]
            AgentGW["agent-gateway.ts"]
            CanvasActions["canvas-actions.ts"]
            ZustandStore["Zustand: alis / auth / ui stores"]
            QueryClient["React Query (queryClient.ts)"]
            RoleConfig["role-config.ts"]
            I18n["i18n/ (kn/mr/ta stubs)"]
        end

        subgraph FESvc["Services (9)"]
            SvcAuth["auth"] & SvcAdmissions["admissions"] & SvcAcademics["academics"]
            SvcExams["examinations"] & SvcFinance["finance"] & SvcHR["hr"]
            SvcAlumni["alumni"] & SvcComms["communication"] & SvcReporting["reporting"]
        end

        subgraph FEHooks["Hooks (12+)"]
            HookAcademics["use-academics"] & HookAdmissions["use-admissions"]
            HookExams["use-examinations"] & HookFinance["use-finance"]
            HookHR["use-hr"] & HookRole["useALISRole"]
            HookAgent["useAgentContext / useAgentCanvasSync"]
        end
    end

    %% ─── NGINX ───
    subgraph NginxLayer["Nginx (Rate Limiting + SSL)"]
        Nginx["nginx/nginx.conf\ninfra/nginx/nginx.conf"]
    end

    %% ─── BACKEND (FastAPI) ───
    subgraph Backend["ALIS/server/ — FastAPI + Python"]
        subgraph ServerRoot["Server Root"]
            MainPy["main.py (/health /ready + CORS)"]
            WorkerPy["worker.py (Celery app + Beat)"]
            DBSvc["db_service.py (execute_query / execute_transaction)"]
            FSSvc["fs_service.py (MinIO-backed)"]
        end

        subgraph APIRouters["API Layer — /api/v1/ (29 routers)"]
            RAuth["auth_router"]
            RAdmissions["admissions_router\n(87 routes, 10 stages)"]
            RAcademics["academics_router"]
            RExams["examinations_router"]
            RFinance["finance_router"]
            RHR["hr_router"]
            RStudent["student_services_router"]
            RAlumni["alumni_router"]
            RComms["communication_router"]
            RReporting["reporting_router"]
            RRoles["roles_router (RBAC delegation)"]
            RWorkflows["workflows_router"]
            RPolicy["policy_router"]
            RProcess["process_engine_router"]
            ROthers["admin / audit / phd / regulatory\nusers / wifi_attendance / convocation\nconsent / gateway / integrations\nintake / organizations / approvals / feature_flags"]
        end

        subgraph CoreInfra["core/ — Cross-Cutting Infrastructure (47 files)"]
            Settings["settings.py (Pydantic)"]
            DomainEvents["domain_events.py (Event Bus)"]
            RBAC["rbac.py"]
            Audit["audit.py (AuditLedger — cross-cutting)"]
            Security["security.py / auth.py / lockdown.py\nmfa_service.py / tenant_crypto.py / vault_client.py"]
            PolicyStack["policy_engine + policy_service\npolicy_store + policy_resolver\npolicy_authoring_agent"]
            ApprovalStack["approvals.py + overrides.py\nescalation.py + hitl.py"]
            WorkflowCore["workflow.py + workflow_schema.py\nstate_registry.py + event_handlers.py"]
            AIStack["ai_gateway.py + llm_router.py\nprompt_registry.py + model_registry.py\ntool_registry.py + guardrails.py\nai_observability.py + shadow_mode.py"]
            Observability["metrics.py + audit.py\ndata_classification.py + diff_tracker.py\nretention_policy.py + error_handlers.py"]
            Utils["feature_flags.py + webhook_dispatcher.py\napi_versioning.py + campus_service.py\nexceptions.py"]
        end

        subgraph DomainModules["Domain Modules (23 modules)"]
            subgraph AdmissionsModule["admissions/ (34 files)"]
                ADM1["S1: lead_service + counsellor_service\n+ counsellor_allocation"]
                ADM2["S2: application_form + automation_pipeline"]
                ADM3["S3: document_verification + deduplication\n+ forgery_detection"]
                ADM4["S4: eligibility_service + eligibility_criteria\n+ intake_quality"]
                ADM5["S5A: entrance_test\nS5B: interview"]
                ADM6["S6: merit_list + seat_matrix_service\n+ policy_engine"]
                ADM7["S7: offer_letter + confirmation"]
                ADM8["S8: payment_v2"]
                ADM9["S9: final_verification + identity_match"]
                ADM10["S10: enrollment_provisioning\n+ enrollment_handover"]
                ADMX["Cross: admissions_templates (25+)\nevent_handlers + review_queue\nreadmission + credit_transfer\nreporting_gate + service"]
            end

            subgraph AcademicsModule["academics/"]
                ACM["course / enrollment / attendance\nfaculty / timetable / OBE\nTA assignment / recalibration"]
            end

            subgraph ExamsModule["examinations/"]
                EXM["schedule / grades / revaluation\ntranscripts / hall_tickets / AI eval guard"]
            end

            subgraph FinanceModule["finance/"]
                FIN["fee_structure / invoicing / dues\nscholarships / exemptions / Tally export"]
            end

            subgraph HRModule["hr/"]
                HRM["staff / payroll / performance\nattendance / leave / visiting_faculty"]
            end

            subgraph StudentSvcModule["student_services/"]
                STU["counselling / grievances\nhostel / library / transport"]
            end

            OtherModules["alumni/ communication/ consent/\nconvocation/ phd/ regulatory/\nmcp/ (NOT the MCP protocol — internal activity bus)\nmigration/ reporting/\nprocess_engine/ tools/ integrations/\nrules/"]
        end

        subgraph AgentsLayer["agents/ — AI Agent Layer (11 subdirs)"]
            AgentRail["rail/\ncontext_advisor (primary interface)"]
            AgentAcademics["academics/\nrisk_detector_v1"]
            AgentAdmissions["admissions/\neligibility"]
            AgentFinance["finance/\ndues_predictor_v1"]
            AgentRegulatory["regulatory/\ncompliance_auditor_v1"]
            AgentResearch["research/\nplagiarism_advisor_v1"]
            AgentStudent["student_services/\ngrievance_classifier_v1"]
            AgentExams["examinations/\nresult_analyzer_v1"]
            AgentHR["hr_admin/\nworkload_analyzer_v1"]
        end

        subgraph ProcessEngine["process_engine/"]
            PEDef["workflow definition"]
            PEExec["executor"]
            PEForms["forms"]
            PEInst["instances"]
        end

        subgraph TaskWorkers["tasks/ — Celery Workers (13)"]
            TAdmissions["admissions"]
            TAI["ai_tasks (inference, policy gen)"]
            TFinance["finance (reconciliation, invoices)"]
            TNotify["notifications (email/SMS/WhatsApp)"]
            TEvents["events (domain event processing)"]
            TCalendar["calendar sync"]
            TBackup["backup"]
            TLMS["lms_sync — NOT IMPLEMENTED"]
            TPlagiarism["plagiarism_poll"]
            TReporting["reporting"]
            TShadow["shadow_divergence"]
            TWebhook["webhook_retry (DLQ)"]
        end
    end

    %% ─── INFRASTRUCTURE ───
    subgraph Infra["Infrastructure"]
        PostgreSQL["PostgreSQL + pgvector"]
        Redis["Redis\n(sessions / rate-limit / cache)"]
        Ollama["Ollama LLM\nEXTRACTION: qwen2.5:1.5b-instruct-q8_0\nEMBEDDINGS: nomic-embed-text\nREASONING: qwen2.5:7b-instruct-q8_0\nGENERATION: qwen2.5:14b-instruct-q8_0 (not yet pulled)"]
        MinIO["MinIO (file storage)"]
        PgBouncer["PgBouncer (connection pool)"]
        CeleryBeat["Celery Beat (scheduler)"]
    end

    subgraph MonitoringStack["infra/monitoring/ — Observability Stack"]
        Prometheus["Prometheus\n(prometheus.yml + alis_alerts.yml)"]
        Grafana["Grafana\n(alis_admissions / alis_domain_events\n/ alis_operations dashboards)"]
        Loki["Loki (loki-config.yml)"]
        Promtail["Promtail (log shipping)"]
        Alertmanager["Alertmanager"]
        Prometheus --> Grafana
        Prometheus --> Alertmanager
        Promtail --> Loki
        Loki --> Grafana
    end

    subgraph DevOps["Scripts & DevOps"]
        SeedPy["ALIS/scripts/seed.py\n(org + SUPER_ADMIN + policies)"]
        OnboardPy["ALIS/scripts/onboard_institution.py"]
        OllamaInstall["ALIS/scripts/install_ollama.sh"]
        LintPy["scripts/lint_alis.py"]
        MockData["scripts/load_mockdata.py"]
        Backup["infra/backup/backup.sh"]
        Locust["infra/loadtest/locustfile.py"]
    end

    subgraph Migrations["ALIS/migrations/ — Alembic (40 versions)"]
        Mig["0001 initial schema\n...\n0040 identity match & access lift"]
    end

    subgraph Tests["ALIS/tests/ (45+ files)"]
        TUnit["Unit tests (958 passing — mocked)"]
        TInteg["@integration tests\n(16 real-DB: 14 core + 2 rail advisor)"]
        TConf["conftest.py\n(TestClient + JWT + fakeredis)"]
    end

    %% ─── CONNECTIONS ───

    %% Clients → Entry Points
    Browser --> Nginx
    DesktopApp -.->|online sync only| Nginx
    DesktopApp -.- ElectronMain
    Webhook --> Nginx
    Nginx --> MainPy

    %% Frontend internal
    ALISShell --> FEPages
    PDash --> FEViews
    FEPages --> FEHooks
    FEPages --> FESvc
    FEHooks --> FELib
    FESvc --> ALISApi
    AgentGW --> ALISApi
    ALISApi --> Nginx

    %% API → Core & Domain
    MainPy --> APIRouters
    APIRouters --> CoreInfra
    APIRouters --> DomainModules
    APIRouters --> AgentsLayer
    APIRouters --> ProcessEngine

    %% Core cross-cutting
    DomainEvents --> TaskWorkers
    DomainEvents --> DomainModules
    Audit -.->|cross-cutting| DomainModules
    Audit -.->|cross-cutting| APIRouters

    %% AI Agents
    AgentsLayer --> AIStack
    AIStack --> Ollama

    %% Domain → Core services
    DomainModules --> PolicyStack
    DomainModules --> ApprovalStack
    DomainModules --> DBSvc
    DomainModules --> FSSvc

    %% Admissions stages
    AdmissionsModule --> ADM1 & ADM2 & ADM3 & ADM4 & ADM5 & ADM6 & ADM7 & ADM8 & ADM9 & ADM10

    %% Celery & Beat
    CeleryBeat --> TaskWorkers
    TaskWorkers --> Redis
    TaskWorkers --> PostgreSQL
    TaskWorkers --> MinIO

    %% DB layer
    DBSvc --> PgBouncer --> PostgreSQL
    FSSvc --> MinIO
    Security --> Redis

    %% Migrations
    Migrations --> PostgreSQL

    %% Monitoring
    Backend -.-> Prometheus
    PostgreSQL -.-> Prometheus

    %% CI/CD
    CICD -.-> Tests

    %% Agent skills assist development
    AgentSkills -.->|dev tooling| Backend
    AgentSkills -.->|dev tooling| Frontend

    %% Style — grayed-out nodes for unimplemented features
    style TLMS fill:#999,color:#fff,stroke:#777