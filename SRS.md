SOFTWARE REQUIREMENTS SPECIFICATION
Text-to-SQL with Clarification Engine

An AI-powered natural-language interface for PostgreSQL databases


Document Item	Details
Document Type	Software Requirements Specification (SRS)
Project	Text-to-SQL with Clarification Engine
Primary DBMS	PostgreSQL
Programming Language	Python
Backend	FastAPI
Validation	Pydantic + SQLGlot
LLM Providers	Gemini / OpenAI / Groq
Deployment	Local / On-Premises
Version	1.0
Status	Proposed

 
Table of Contents
1.	1. Introduction
2.	2. Overall Description
3.	3. System Scope
4.	4. Existing Problem and Motivation
5.	5. Proposed System
6.	6. System Architecture
7.	7. Functional Requirements
8.	8. Non-Functional Requirements
9.	9. External Interface Requirements
10.	10. Technology Stack
11.	11. Database Requirements
12.	12. AI / LLM Requirements
13.	13. Clarification Engine Specification
14.	14. Text-to-SQL Generation Specification
15.	15. SQL Validation and Security
16.	16. User Roles
17.	17. Use Cases
18.	18. Data Flow
19.	19. Error Handling
20.	20. Testing and Evaluation
21.	21. Constraints and Assumptions
22.	22. Risks and Mitigation
23.	23. Future Scope
24.	24. Acceptance Criteria
 
1. Introduction
1.1 Purpose
This Software Requirements Specification defines the requirements for a local, AI-powered Text-to-SQL with Clarification Engine. The system enables users to query a PostgreSQL database using natural language instead of writing SQL manually. Unlike a basic Text-to-SQL system, the proposed system detects ambiguity, missing constraints, and unclear terminology and asks targeted clarification questions before generating SQL.
1.2 Intended Audience
•	Project developers and implementation team.
•	Project guide, evaluator, and academic reviewers.
•	Database administrators and technical users.
•	Researchers evaluating natural-language database interfaces.
•	End users who need database information without extensive SQL knowledge.
1.3 Definitions and Acronyms
Term	Definition
Text-to-SQL	Conversion of natural-language questions into executable SQL queries.
Clarification Engine	Component that identifies ambiguity or missing information and asks the user targeted questions.
Schema	Structure of a database including tables, columns, keys, relationships, and data types.
Schema Linking	Mapping natural-language concepts to actual database tables and columns.
LLM	Large Language Model used for language understanding and SQL generation.
SQL Validation	Checking generated SQL for syntax, schema, semantic, and security constraints.
Pydantic	Python library used to validate structured application and AI outputs.
SQLGlot	SQL parser/transpiler used to parse and inspect generated SQL.
PostgreSQL	Primary relational database management system used by the project.

2. Overall Description
2.1 Product Perspective
The product is a local application consisting of a user interface, a Python/FastAPI backend, a PostgreSQL database, and an AI orchestration layer. The application may use Gemini, OpenAI, or Groq as interchangeable LLM providers. The system is not dependent on cloud deployment of the application. If an external LLM API is selected, only the model inference call requires internet connectivity.
2.2 Product Functions
•	Accept natural-language database questions.
•	Understand user intent and extract query requirements.
•	Retrieve relevant PostgreSQL schema information.
•	Detect ambiguity and missing information.
•	Generate clarification questions and options.
•	Maintain clarification state across multiple turns.
•	Generate PostgreSQL-compatible SQL.
•	Validate SQL before execution.
•	Prevent destructive or unauthorized database operations.
•	Execute approved read-only queries.
•	Display query results in a structured form.
•	Provide a natural-language explanation of results.
•	Maintain query and clarification history.
•	Support configurable LLM providers for experimentation and comparison.
2.3 User Characteristics
•	Beginner users with little or no SQL knowledge.
•	Students and analysts performing database exploration.
•	Technical users who want faster query construction.
•	Administrators responsible for configuring the local PostgreSQL database.
3. System Scope
3.1 In Scope
•	PostgreSQL as the primary and supported DBMS for Version 1.
•	Natural-language query processing.
•	Ambiguity detection and interactive clarification.
•	Schema inspection and schema linking.
•	PostgreSQL SQL generation.
•	SQL syntax and security validation.
•	Read-only query execution.
•	Result display and basic explanation.
•	Local deployment on Windows or another supported desktop environment.
•	Comparison of LLM providers where API access is available.
3.2 Out of Scope for Version 1
•	Cloud hosting or cloud database deployment.
•	Automatic modification of database records.
•	Support for every SQL dialect.
•	Training a foundation LLM from scratch.
•	Unrestricted execution of INSERT, UPDATE, DELETE, DROP, ALTER, or TRUNCATE.
•	Autonomous database administration.
•	Guaranteed correctness for every natural-language query.
4. Existing Problem and Motivation
Traditional database interfaces require users to know SQL syntax and database structure. Basic Text-to-SQL systems reduce this requirement but may produce incorrect SQL when the natural-language request is ambiguous or incomplete.
Existing Problem	Example	Proposed Response
SQL knowledge requirement	User does not know JOIN or GROUP BY syntax.	Generate SQL from natural language.
Ambiguous metric	"Show the highest sales."	Ask whether sales means revenue, units, or transactions.
Ambiguous entity	"Show sales from Mumbai."	Ask whether Mumbai refers to customer, store, or transaction location.
Missing time period	"Show revenue."	Ask for a time period if required by the selected analysis.
Schema mismatch	LLM invents a column.	Validate against actual PostgreSQL schema.
Incorrect joins	Tables are joined using unrelated fields.	Use primary/foreign-key relationships and schema linking.
Unsafe SQL	Generated SQL contains DELETE/DROP.	Allow-list read-only operations and use a read-only DB account.
Poor explainability	Only raw SQL is shown.	Show interpretation, SQL, and result explanation.

5. Proposed System
The proposed system follows an ambiguity-aware pipeline. The user submits a natural-language question. The system analyzes intent, retrieves relevant schema information, determines whether clarification is necessary, and asks the smallest useful clarification question. Once the query is sufficiently specified, the system generates PostgreSQL SQL, validates it, executes it using a read-only connection, and presents the result.
5.1 Example
User: "Show the top performing students."
System: "How should student performance be measured?"
•	Total marks
•	Average marks
•	Percentage
•	Attendance
User: "Total marks."
The system then retrieves the relevant student and marks schema and generates a validated PostgreSQL query.
6. System Architecture
Logical architecture:
25.	User Interface (React/TypeScript or equivalent local UI)
26.	FastAPI backend
27.	Query Understanding Module
28.	Ambiguity Detection Module
29.	Clarification Engine
30.	PostgreSQL Schema Retrieval Module
31.	Schema Linking Module
32.	LLM Provider Adapter (Gemini / OpenAI / Groq)
33.	Pydantic Structured Output Validation
34.	SQL Generation Module
35.	SQLGlot SQL Validation
36.	Security / Read-Only Execution Layer
37.	PostgreSQL Database
38.	Result Processing and Explanation Module
High-level flow: Natural Language Query → Intent Analysis → Ambiguity Detection → Clarification (if required) → Schema Retrieval → Schema Linking → SQL Generation → Pydantic/format validation → SQLGlot parsing and validation → Security checks → PostgreSQL execution → Result Processing → User.
7. Functional Requirements
ID	Requirement	Description
FR-01	Natural Language Input	The system shall accept natural-language questions from the user.
FR-02	Intent Analysis	The system shall identify the intended analytical operation, entities, metrics, filters, grouping, ordering, and time constraints where possible.
FR-03	Schema Retrieval	The system shall retrieve relevant PostgreSQL tables, columns, data types, keys, and relationships.
FR-04	Ambiguity Detection	The system shall detect ambiguous or incomplete query requirements.
FR-05	Clarification Generation	The system shall generate concise clarification questions and, where possible, selectable options.
FR-06	Clarification State	The system shall retain previous query context and user clarification responses within a query session.
FR-07	Query Rewriting	The system shall combine the original question and clarification responses into a resolved query representation.
FR-08	SQL Generation	The system shall generate PostgreSQL-compatible SQL using only authorized schema information.
FR-09	Structured AI Output	The system shall validate structured model responses using Pydantic schemas.
FR-10	SQL Parsing	The system shall parse generated SQL using SQLGlot or an equivalent parser.
FR-11	SQL Security	The system shall reject destructive or unauthorized SQL operations.
FR-12	Read-Only Execution	The system shall execute approved queries using a PostgreSQL read-only database account.
FR-13	Error Recovery	The system shall handle invalid SQL or execution errors without crashing the application.
FR-14	Result Display	The system shall display returned rows in a structured table.
FR-15	Result Explanation	The system shall provide a concise explanation based on the executed result.
FR-16	SQL Transparency	The system shall optionally display the generated SQL to the user.
FR-17	Query History	The system shall store query sessions and clarification history where enabled.
FR-18	Provider Selection	The system should support configurable LLM providers such as Gemini, OpenAI, and Groq.

8. Non-Functional Requirements
ID	Category	Requirement
NFR-01	Performance	The system should provide responsive interaction for normal-sized local PostgreSQL databases and should report model/database latency.
NFR-02	Reliability	A model or SQL error shall produce a controlled error message or recovery attempt rather than an application crash.
NFR-03	Security	Database credentials shall not be exposed in frontend code or logs.
NFR-04	Security	Database execution shall use a least-privilege/read-only account for generated queries.
NFR-05	Maintainability	The backend shall be modular so LLM providers and validation components can be replaced.
NFR-06	Usability	Clarification questions shall be understandable to non-SQL users.
NFR-07	Portability	The application shall run locally on a supported Windows development machine.
NFR-08	Auditability	The system should retain sufficient query/clarification metadata for debugging and evaluation.
NFR-09	Scalability	The design should allow larger schemas to be handled through selective schema retrieval.
NFR-10	Privacy	The application shall clearly distinguish local processing from data sent to external LLM APIs.

9. External Interface Requirements
9.1 User Interface
•	Natural-language query input box.
•	Clarification question area.
•	Selectable clarification options where appropriate.
•	Conversation/query session display.
•	Generated SQL panel.
•	Result table.
•	Optional charts for suitable result sets.
•	Error and validation messages.
•	Query history.
9.2 Backend API
Method	Endpoint	Purpose
POST	/api/query	Submit a new natural-language query.
POST	/api/query/{id}/clarify	Submit a clarification response.
POST	/api/query/{id}/generate	Generate or regenerate SQL.
POST	/api/query/{id}/execute	Execute validated SQL.
GET	/api/schema	Retrieve database schema metadata.
GET	/api/query/history	Retrieve query history.
GET	/api/query/{id}	Retrieve a query session.

10. Technology Stack
Technology	Role	Reason
Python	Core development	Suitable for AI, database, validation, and API development.
PostgreSQL	Primary DBMS	Relational database used for project data and target queries.
FastAPI	Backend API	Lightweight Python API framework with strong type support.
Pydantic	Structured validation	Validates request, response, and model-generated structured data.
Gemini	LLM provider	Natural-language understanding and SQL generation option.
OpenAI	LLM provider	Alternative LLM provider for generation and comparison.
Groq	LLM provider	Alternative provider suitable for low-latency inference where supported.
SQLGlot	SQL parser/validator	Parses SQL and helps enforce dialect-aware validation.
psycopg	PostgreSQL driver	Python connection to PostgreSQL.
React + TypeScript	Frontend	Interactive local web interface.

11. Database Requirements
11.1 Target Database
PostgreSQL is the only target DBMS for Version 1.
11.2 Schema Metadata
•	Table names.
•	Column names and data types.
•	Primary keys.
•	Foreign keys.
•	Nullable attributes where available.
•	Relevant indexes where available.
•	Relationships required for join reasoning.
11.3 Application Tables
Table	Important Fields	Purpose
users	id, name, email, role	Application users.
query_sessions	id, user_id, original_query, status, created_at	Stores query sessions.
clarifications	id, session_id, question, response, resolved_at	Stores clarification turns.
generated_queries	id, session_id, sql_text, validation_status	Stores generated SQL and validation state.
query_executions	id, query_id, row_count, execution_time, status	Stores execution metadata.

12. AI / LLM Requirements
12.1 LLM Responsibilities
•	Interpret natural-language questions.
•	Identify query intent.
•	Identify potentially ambiguous concepts.
•	Generate clarification questions.
•	Generate structured query plans.
•	Generate PostgreSQL SQL from resolved requirements.
•	Explain validated results.
12.2 Provider Abstraction
The backend should use a provider abstraction so that Gemini, OpenAI, and Groq can be selected without changing the rest of the application. The application should not depend on provider-specific response formats internally.
12.3 Structured Output
Example conceptual Pydantic model:
QueryAnalysis: intent, is_ambiguous, ambiguity_type, missing_information, clarification_question, clarification_options, entities, filters, metric, grouping, ordering.
13. Clarification Engine Specification
The Clarification Engine is the distinguishing component of the system. It should avoid asking unnecessary questions and should ask only those questions that materially affect the SQL interpretation.
13.1 Ambiguity Categories
•	Metric ambiguity: e.g., sales could mean revenue, units, or transactions.
•	Entity ambiguity: e.g., customer, product, employee, or store.
•	Time ambiguity: e.g., recent, last year, financial year, or a specific date range.
•	Filter ambiguity: e.g., active, high-value, premium, or top without a defined threshold.
•	Aggregation ambiguity: total, average, maximum, minimum, count, or distinct count.
•	Relationship ambiguity: multiple possible tables or join paths.
•	Scope ambiguity: all records versus a specific region, category, or group.
13.2 Clarification Rules
•	Ask the smallest number of questions required to resolve material ambiguity.
•	Prefer clear options when the possible interpretations can be enumerated.
•	Do not ask for information already present in the query or known from session context.
•	Use database schema information when generating clarification options.
•	Retain clarification responses in the current session.
•	Regenerate the query plan after clarification if the answer changes the interpretation.
14. Text-to-SQL Generation Specification
The SQL generation prompt/context should contain:
•	Resolved natural-language query.
•	Relevant PostgreSQL schema.
•	Table relationships.
•	Relevant data types.
•	Clarification responses.
•	PostgreSQL dialect requirement.
•	Read-only execution restrictions.
•	Instruction not to invent tables or columns.
14.1 Generation Rules
•	Use only tables and columns supplied by schema retrieval.
•	Use valid PostgreSQL syntax.
•	Prefer explicit JOIN conditions.
•	Use appropriate aggregation and GROUP BY clauses.
•	Apply user-specified filters exactly.
•	Use parameterized values where application architecture supports them.
•	Do not generate destructive statements for normal user queries.
15. SQL Validation and Security
15.1 Validation Pipeline
39.	Parse generated SQL.
40.	Check SQL statement type.
41.	Reject destructive or unauthorized operations.
42.	Verify referenced tables and columns against PostgreSQL schema metadata.
43.	Validate joins and required relationships where possible.
44.	Check for obvious semantic inconsistencies.
45.	Apply execution limits/timeouts where feasible.
46.	Execute only after all required checks pass.
15.2 Database Security
•	Use a dedicated read-only PostgreSQL role for generated queries.
•	Do not store plaintext database passwords in source code.
•	Use environment variables or a secure local configuration mechanism for secrets.
•	Do not return raw credentials in API responses.
•	Limit database permissions to the minimum required schema/tables.
•	Record security validation failures for debugging without exposing secrets.
16. User Roles
Role	Permissions
Administrator	Configure local database connection, inspect schema, manage application settings, review logs/history.
User	Submit natural-language queries, answer clarification questions, view SQL/results, view own query history.

17. Use Cases
ID	Use Case	Actor Action	System Response
UC-01	Submit Query	User enters a natural-language database question.	System analyzes and continues or requests clarification.
UC-02	Answer Clarification	User selects or enters an answer.	System updates the query context and continues processing.
UC-03	Generate SQL	Resolved query is sent to SQL generation.	PostgreSQL SQL is produced.
UC-04	Validate SQL	Generated SQL enters validation.	System accepts or rejects the query.
UC-05	Execute Query	Validated read-only SQL is executed.	Results are returned.
UC-06	View Explanation	User views result.	System summarizes the result using returned data.
UC-07	View History	User opens previous queries.	System displays prior query sessions and outcomes.

18. Data Flow
Level 0:
User → Text-to-SQL/Clarification Engine → PostgreSQL → Results → User
Level 1:
47.	User submits natural-language query.
48.	Backend receives and validates request.
49.	Query Understanding analyzes intent and entities.
50.	Schema Retrieval obtains relevant PostgreSQL metadata.
51.	Ambiguity Detection determines whether the request is sufficiently specified.
52.	Clarification Engine asks a question if required.
53.	Resolved Query Planner creates a structured representation.
54.	LLM generates PostgreSQL SQL.
55.	Pydantic validates structured model output.
56.	SQLGlot parses and validates SQL.
57.	Security layer checks allowed operations.
58.	PostgreSQL executes the approved query.
59.	Result Processor formats data.
60.	System displays results and explanation.
19. Error Handling
Error	Expected Handling
Empty query	Ask the user to provide a question.
Ambiguous query	Trigger clarification.
Unrecognized schema term	Attempt schema-aware clarification or request clarification.
Invalid model output	Reject structured output and retry/fail safely.
Invalid SQL syntax	Do not execute; regenerate or show controlled error.
Unknown table/column	Do not execute; provide schema-aware correction/retry.
Unauthorized SQL operation	Reject query and inform user that only read operations are permitted.
Database connection failure	Show a connection error without exposing credentials.
Query timeout	Cancel/stop execution where supported and report timeout.
No results	Display an empty-result message and optionally suggest query refinement.
LLM provider failure	Return controlled provider error or allow another configured provider.

20. Testing and Evaluation
20.1 Testing Levels
•	Unit testing for query parsing, clarification rules, schema retrieval, validation, and utility functions.
•	Integration testing for FastAPI + PostgreSQL.
•	LLM integration testing for provider adapters.
•	Security testing for destructive SQL and unauthorized operations.
•	End-to-end testing from user question to result.
•	Usability testing for clarification questions.
20.2 Evaluation Metrics
Metric	Purpose
SQL Execution Accuracy	Percentage of generated queries that execute successfully and answer the intended task.
Exact SQL Match	Comparison with reference SQL where a reference exists.
Ambiguity Detection Accuracy	Correct identification of queries requiring clarification.
Clarification Success Rate	Percentage of ambiguous queries resolved after clarification.
Invalid SQL Rate	Percentage of generated SQL rejected due to syntax/schema problems.
Average Clarification Turns	Number of clarification interactions needed per ambiguous query.
Latency	Time from user query to clarification or final result.
Provider Comparison	Comparison of supported LLM providers using the same evaluation set.

21. Constraints and Assumptions
•	PostgreSQL is the target DBMS for Version 1.
•	The system assumes that the database schema is accessible to the schema retrieval component.
•	The execution account is assumed to have only the permissions required for safe read operations.
•	LLM output is treated as untrusted and must be validated.
•	External LLM providers may have their own rate limits, usage policies, latency, and privacy implications.
•	Local deployment performance depends on the user's hardware and database size.
•	The system cannot guarantee correct interpretation for every ambiguous natural-language question.
22. Risks and Mitigation
Risk	Impact	Mitigation
LLM generates incorrect SQL	High	Schema grounding, SQLGlot validation, read-only execution, evaluation dataset.
LLM hallucinates schema	High	Supply retrieved schema and validate table/column references.
Ambiguity not detected	High	Explicit ambiguity categories and evaluation set.
Too many clarification questions	Medium	Optimize for minimum necessary clarification turns.
External API unavailable	Medium	Provider abstraction and controlled error handling.
Sensitive schema sent to external API	High	Document data flow, minimize context, optionally support local LLM.
Slow database query	Medium	Read-only role, query limits/timeouts, validation and optimization checks.
Credential leakage	High	Environment variables/local secrets and no credential logging.

23. Future Scope
•	Support additional SQL dialects such as MySQL and SQL Server.
•	Add schema embedding/vector retrieval for very large databases.
•	Add local LLM support through a local inference runtime.
•	Add advanced chart recommendations based on result structure.
•	Add semantic caching for repeated queries.
•	Add query cost estimation and optimization suggestions.
•	Add domain-specific terminology dictionaries.
•	Add voice-based natural-language querying.
•	Add fine-tuned Text-to-SQL models.
•	Add benchmark datasets and automated regression evaluation.
24. Acceptance Criteria
61.	A user can enter a natural-language query against the configured PostgreSQL database.
62.	The system can retrieve relevant database schema information.
63.	The system can identify at least the major ambiguity categories defined in this SRS.
64.	For an ambiguous query, the system asks a relevant clarification question before final SQL generation.
65.	The system retains the user's clarification response.
66.	The system generates PostgreSQL-compatible SQL for supported query types.
67.	Generated SQL is parsed and validated before execution.
68.	Destructive SQL statements are rejected.
69.	Queries are executed using a read-only PostgreSQL account.
70.	The system displays the query result without exposing database credentials.
71.	The system handles invalid SQL, database errors, and LLM errors gracefully.
72.	The system records sufficient information to evaluate query generation and clarification performance.
73.	The project can run locally without cloud deployment of the application.
Appendix A – Example Query Scenarios
User Query	Ambiguity	Clarification	Expected Outcome
Show the highest sales.	Metric/grouping/time may be unclear.	What should be used to measure sales?	Resolved metric followed by SQL generation.
Show top students.	Top by what measure?	Should performance be based on total marks, percentage, or another measure?	SQL ranking students by selected metric.
Show sales from Mumbai.	Which location field?	Should Mumbai refer to customer, store, or transaction location?	SQL using selected location field.
Show revenue last year.	May require calendar/fiscal interpretation.	Do you mean the previous calendar year or financial year?	SQL using resolved date range.
How many customers do we have?	Usually clear.	No clarification required.	COUNT query against customer entity.

Appendix B – Recommended Development Phases
74.	Phase 1: PostgreSQL connection and schema extraction.
75.	Phase 2: FastAPI backend and basic query API.
76.	Phase 3: LLM provider integration.
77.	Phase 4: Pydantic structured query analysis.
78.	Phase 5: Clarification engine.
79.	Phase 6: PostgreSQL SQL generation.
80.	Phase 7: SQLGlot validation and security layer.
81.	Phase 8: Query execution and result display.
82.	Phase 9: Frontend and query history.
83.	Phase 10: Testing, benchmark dataset, and provider comparison.
Appendix C – Proposed Project Objective
To design and develop an ambiguity-aware Text-to-SQL system that enables non-technical users to query PostgreSQL databases using natural language, automatically detects insufficient or ambiguous requirements, asks targeted clarification questions, generates validated PostgreSQL SQL, executes it safely, and presents understandable results.
