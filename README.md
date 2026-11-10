# 🧠 Text-to-SQL with Clarification Engine

[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-009688?style=flat&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Python](https://img.shields.io/badge/Python-3.10%2B-3776AB?style=flat&logo=python&logoColor=white)](https://www.python.org)
[![PostgreSQL](https://img.shields.io/badge/Database-PostgreSQL%20%7C%20SQLite-336791?style=flat&logo=postgresql&logoColor=white)](https://www.postgresql.org)
[![Gemini](https://img.shields.io/badge/LLM-Google%20Gemini-4285F4?style=flat&logo=google&logoColor=white)](https://ai.google.dev)
[![Scikit-Learn](https://img.shields.io/badge/ML-Scikit--Learn%20(Local%20NLP)-F7931E?style=flat&logo=scikit-learn&logoColor=white)](https://scikit-learn.org)
[![Security](https://img.shields.io/badge/SQL%20Security-SQLGlot%20AST%20Guardrails-green?style=flat)](https://github.com/tobymao/sqlglot)

> An enterprise-grade, conversational Text-to-SQL system powered by **Interactive Ambiguity Detection**, **Universal Domain Formulas**, **AST-level Security Guardrails**, and **Multi-Tenant Data Isolation**.

---

## 📌 Overview

Traditional Text-to-SQL tools make dangerous assumptions when presented with ambiguous or underspecified queries. For example, asking *"Show me the top bowlers"* without specifying a metric could mean most wickets, best economy, or lowest bowling average.

The **Text-to-SQL with Clarification Engine** solves this fundamentally:
1. **Detects Ambiguities** before any SQL query is drafted.
2. **Engages the User** with concise, targeted multi-choice clarification questions.
3. **Applies Universal Domain Formulas** (Cricket/IPL analytics, financial metrics, physics & statistical equations).
4. **Validates SQL through AST Parsers** ensuring strict read-only execution, schema validation, and SQL-injection prevention.
5. **Operates in Hybrid Mode** — leveraging cloud LLMs (Google Gemini) with automatic fallback to a self-contained, 100% offline local Scikit-Learn NLP model.

---

## ✨ Key Features

### 1. 🔍 Clarification Intelligence & Reasoning Transparency
- **Smart Scoring, Execution-Divergence & What-If Previews**: Scores ambiguity (`0.0–1.0`), suppresses redundant questions when candidate SQL probes produce identical results, and annotates options with live DB values and estimated row counts (`~N rows`).
- **Modes (`Smart`, `Strict`, `Ask-After-Answer`)**: Executes low-ambiguity/best-guess interpretations immediately in **Ask-After-Answer** mode with instant alternative pills, or pauses upfront in **Strict** mode.
- **Think $\to$ Analyze $\to$ Verify $\to$ Synthesize Reasoning**: Collapsible thought-process timeline, **Assumption Ledger** (one-click alternative re-runs), **Query Provenance** (phrase $\to$ SQL clause mapping), **Confidence Reasons** popover, and quantitative figure synthesis.
- **Zero-Hallucination Schema-Gap Guard & Calibration**: Detects out-of-schema entities before SQL generation and supports example-based calibration (`"expected around ..."`).
- **Dynamic Ambiguity Detection**: Detects `order_status` scope filters, undefined business metrics (`churn`, `retention`, `conversion rate`), and multi-FK join path ambiguity across schema relationships.

### 2. 🧩 Power BI–Style Table Relationship Diagram (Model View)
- **Interactive ERD Canvas**: Drag table cards, pan/zoom canvas, drag between column ports to create joins manually, configure cardinality (`1:1`, `1:N`, `N:1`, `N:N`), toggle active state / cross-filter direction, and auto-detect matching keys across tables.
- **Visual Schema Column Picker**: Click `🔍` on any column in **Model View** to launch an Assistant prompt directly for that field.
- **Direct NLP Graph Integration**: Multi-table SQL generation reads active manual and foreign-key relationships in real time.

### 3. 🧠 Semantic Memory, Team Glossary, Governance & Quality Metrics
- **Personal Semantic Memory & Clarification Replay**: Learns confirmed interpretations per authenticated user with both temporal decay and schema-fingerprint invalidation.
- **Self-Growing Team Glossary & Personas**: Propose/approve business definitions (`Honors`, custom metrics) and switch role personas (`general`, `finance`, `marketing`, `operations`, `academic`).
- **Safety, PII & Quality Hub**: Read-only SQLGlot AST guardrails, query scan cost estimation (`EXPLAIN`), `NULL`-rate data-quality warnings, PII detection & masking (`Mask PII` toggle), immutable audit logs, and clarification quality metrics (Clarification Rate, Question Usefulness, Avg Resolution Turns, Silent Failure Rate).

### 4. 🧮 Universal Domain Formula & Calculation Engine
Built-in domain intelligence capable of answering complex analytical calculations:
- 🏏 **Cricket & Sports Analytics**: Bowling strike rate, batting strike rate, bowling average, economy rate, boundary percentage, head-to-head match breakdowns (`CSK vs MI`), and toss statistics.
- 💼 **Finance & Business**: ROI, CAGR, Gross/Operating Margin, Net Present Value (NPV), Break-even point, EBITDA.
- 📐 **Mathematics & Statistics**: Standard Deviation, Variance, Pearson Correlation, Z-Score, Euclidean Distance, Exponential Growth.
- ⚙️ **Physics & Science**: Kinetic/Potential Energy, Force, Velocity/Acceleration, Ohm's Law, Gravitational Attraction, Work & Power.
- 🌍 **Geography & Conversions**: Haversine distance, speed/length/temperature unit conversions.

### 5. ⚡ Hybrid Dual-Provider Architecture (Upgraded Offline Ensemble)
- **Local Self-Learning NLP Ensemble**: `FeatureUnion` (`word` 1–3 n-grams + `char_wb` 3–5 n-grams) + Balanced Soft-Voting Ensemble (`LogisticRegression` + `CalibratedClassifierCV(LinearSVC)` + `ComplementNB`) trained on `282` domain seeds (`77.0%` Stratified K-Fold CV accuracy, `75.9%` CV Weighted F1) with table/schema-gated semantic replay.
- **Gemini AI Provider & Zero-Downtime Fallback**: High-reasoning cloud LLM option with automatic local failover.

### 6. 👥 Multi-Tenancy, Workspace Isolation & CSV/Excel Ingestion
- **Authentication & Isolation**: Salted SHA-256 credentials, bearer session tracking, per-user uploaded datasets in persistent SQLite (`data/local_warehouse.db`), and tenant-scoped clarification replays/glossary terms.
- **Drag-and-Drop Ingestion**: Automatically creates tables, detects schema types, and indexes uploaded `.csv`, `.xlsx`, and `.sql` files.

---

## 🏛️ System Architecture

```mermaid
flowchart TD
    User([User / Browser]) <--> UI[Flagship Modern Web UI]
    UI <--> API[FastAPI Backend Server]

    subgraph Authentication & Isolation
        Auth[Auth Manager] --> Session[Multi-Tenant Session Store]
        Session --> UserData[Isolated User Schemas & Uploads]
    end

    subgraph Processing Pipeline
        API --> Ambiguity[Ambiguity Detector]
        Ambiguity -- Ambiguous --> Clarify[Clarification Prompt Engine]
        Clarify --> UI
        
        Ambiguity -- Clear / Answered --> Formula[Universal Formula Engine]
        Formula --> Router{LLM / NLP Router}
        
        Router -->|Cloud Online| Gemini[Google Gemini API]
        Router -->|Local Offline / Fallback| LocalNLP[Scikit-Learn NLP Engine]
    end

    subgraph Security & Execution
        Gemini --> Validator[SQLGlot AST Validator]
        LocalNLP --> Validator
        Validator --> Guardrails[Read-Only & Safety Enforcer]
        Guardrails --> DB[(PostgreSQL / SQLite DBMS)]
        DB --> Results[Structured Data & Visual Table View]
    end

    Results --> UI
```

---

## 📁 Repository Structure

```text
├── backend/
│   ├── main.py                     # FastAPI application entrypoint & lifespan
│   ├── config.py                   # Pydantic environment configuration & settings
│   ├── database/
│   │   ├── connection.py           # Database connection manager (PostgreSQL / SQLite)
│   │   ├── schema_extractor.py     # Real-time schema inspection & linking
│   │   └── file_ingestion.py       # CSV and Excel file ingestion engine
│   ├── llm/
│   │   ├── base.py                 # Abstract LLM provider interface
│   │   ├── factory.py              # Provider factory with dynamic fallbacks
│   │   ├── gemini_provider.py      # Google Gemini integration
│   │   └── local_nlp_provider.py   # Offline Scikit-Learn NLP engine
│   ├── modules/
│   │   ├── ambiguity.py                # Ambiguity detection & dynamic schema checks
│   │   ├── clarification.py            # Session state & clarification rewrite turns
│   │   ├── clarification_intelligence.py # Divergence, grounding, assumptions, confidence & thinking
│   │   ├── semantic_memory.py          # Personal memory decay, glossary workflow & personas
│   │   ├── governance.py               # Cost guardrails, NULL scan, PII masking & metrics
│   │   ├── relationship_manager.py     # Manual/auto-detected schema joins & ERD layouts
│   │   ├── formula_engine.py           # Multi-domain calculation algorithms
│   │   ├── learning_engine.py          # Word+Char TF-IDF + Balanced Voting Ensemble
│   │   ├── nlp_engine.py               # Schema-linking SQL synthesis & precision figures
│   │   ├── auth_manager.py             # Multi-tenant user auth & session management
│   │   └── conversation_manager.py     # Persistent conversation & metadata storage
│   └── routers/
│       ├── auth.py                     # Authentication API endpoints
│       ├── query.py                    # Query, clarification, & intelligence pipeline
│       ├── schema.py                   # Schema inspection & relationship endpoints
│       ├── governance.py               # Memory, glossary, persona, audit & quality API
│       ├── model.py                    # ML model status, training & feedback routes
│       └── upload.py                   # Dataset upload & management routes
├── data/
│   ├── models/                         # Trained joblib ensemble binaries & CV metrics
│   └── team_glossary.json              # Approved default business glossary seeds
├── frontend/
│   ├── index.html                      # Assistant, Model View & Intelligence Hub UI
│   ├── style.css                       # Apple HIG theme styling
│   ├── app.js                          # Client-side state, auth, and query controller
│   ├── erd_diagram.js                  # Interactive Power BI-style ERD canvas
│   └── intelligence_ui.js              # Thought process, ledger, provenance & governance UI
├── tests/                              # Backend & Clarification Intelligence suites (41 core tests)
├── .gitignore                          # Git exclusion rules for secrets, DBs & runtime logs
├── requirements.txt                    # Python package dependencies
└── README.md                           # Project documentation
```

---

## 🚀 Quick Start

### 1. Prerequisites
- **Python 3.10+**
- **Git**
- *(Optional)* PostgreSQL 14+ installed locally (SQLite is supported out-of-the-box for uploaded datasets).

### 2. Clone the Repository
```bash
git clone https://github.com/Raj-15042006/Text-To-SQL-with-Clarification-Engine.git
cd Text-To-SQL-with-Clarification-Engine
```

### 3. Create and Activate a Virtual Environment
```bash
# Windows (cmd / Git Bash)
python -m venv .venv
source .venv/Scripts/activate

# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
```

### 4. Install Dependencies
```bash
pip install -r requirements.txt
```

### 5. Run the Application
```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

Open your browser and navigate to:
- **Web Interface**: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- **Interactive OpenAPI Docs**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

---

## 🧪 Running Tests

The test suite covers unit tests, multi-tenancy isolation, ambiguity resolution, domain formulas, and API endpoints:

```bash
# Run all tests
python -m pytest tests/ -v
```

---

## 💡 Example Queries & Interaction Flows

### 1. Ambiguity Clarification Flow
> **User**: *"Show me the top students."*  
> **Clarification Engine**: Detects missing metric and sorting criteria.  
> **Prompt**: *"Which metric would you like to rank students by?"*  
> **Options**: `[Highest Total Marks]`, `[Highest Percentage]`, `[By Specific Course]`  
> **User selects**: `[Highest Total Marks]`  
> **Generated SQL**:
> ```sql
> SELECT s.student_id, s.name, SUM(m.score) AS total_score
> FROM students s
> JOIN marks m ON s.student_id = m.student_id
> GROUP BY s.student_id, s.name
> ORDER BY total_score DESC
> LIMIT 10;
> ```

### 2. Domain Formula Query (Sports Analytics)
> **User**: *"Calculate the bowling strike rate of CSK throughout the season."*  
> **Formula Engine**: Applies $\text{Bowling Strike Rate} = \frac{\text{Balls Bowled}}{\text{Wickets Taken}}$ specifically filtered for CSK bowlers across all matches.

### 3. Business Financial Analytics
> **User**: *"Compute operating profit margin by region for Q3."*  
> **Generated SQL**:
> ```sql
> SELECT region, 
>        ROUND(((SUM(operating_income) / NULLIF(SUM(total_revenue), 0)) * 100)::numeric, 2) AS operating_margin_pct
> FROM enterprise_financials
> WHERE quarter = 'Q3'
> GROUP BY region
> ORDER BY operating_margin_pct DESC;
> ```

---

## 🔒 Security & Privacy

- **Zero Data Leakage**: `.env` and local database files are protected and ignored by `.gitignore`.
- **Injection Prevention**: Queries pass through SQLGlot AST validation; multi-statement attacks, comments, and injection vectors are discarded.
- **Permission Bounding**: Backend executes all user queries through a read-only database cursor with execution timeouts.

---

## 📜 License

This project is licensed under the **MIT License** — feel free to use, modify, and distribute.

