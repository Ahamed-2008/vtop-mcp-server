# VTOP Endpoint Discovery

A network traffic discovery, schema analysis, and classification tool for identifying the HTTP endpoints, request parameters, and response structures used by the VIT VTOP student portal.

This project is the foundational discovery component of a larger **VTOP MCP Server** architecture that enables AI assistants to interface with student data through the Model Context Protocol (MCP).

---

## Table of Contents

* [Overview](#overview)
* [Design Philosophy](#design-philosophy)
* [Analysis Pipeline](#analysis-pipeline)
* [Key Capabilities](#key-capabilities)
  * [1. Request Schema Analysis](#1-request-schema-analysis)
  * [2. HTML & JSON Response Analysis](#2-html--json-response-analysis)
  * [3. Multi-Signal Evidence-Based Classification](#3-multi-signal-evidence-based-classification)
  * [4. Structural Deduplication](#4-structural-deduplication)
  * [5. Clean Specification vs Raw Captures](#5-clean-specification-vs-raw-captures)
  * [6. Privacy & Strict Redaction](#6-privacy--strict-redaction)
* [Discovery Modes](#discovery-modes)
  * [Automated Web Crawler Mode](#automated-web-crawler-mode-default)
  * [Guided Discovery Wizard](#guided-discovery-wizard)
* [Installation](#installation)
* [Usage & CLI Options](#usage--cli-options)
* [Output Schema Example](#output-schema-example)
* [Catalog Diffing Utility](#catalog-diffing-utility)
* [Running Tests](#running-tests)
* [Disclaimer](#disclaimer)

---

## Overview

When interacting with VTOP (vtop.vit.ac.in), browsers communicate with backend servers through dynamic HTTP requests (form posts, JSON XHR/fetch calls, and HTML page loads).

The **VTOP Endpoint Discovery** tool:
1. Opens an interactive Playwright Chromium browser.
2. Lets you log in securely with your credentials and CAPTCHA.
3. Automatically or interactively navigates portal sections (Attendance, Marks, Timetable, Courses, Profile, Exams, History).
4. Intercepts, filters, deduplicates, and analyzes traffic into a clean endpoint catalog.

---

## Design Philosophy

* **Capture first. Understand second. Automate third.**
* **Not a login bot**: The tool never automates password typing or captcha solving.
* **Never persist secrets**: Passwords, session cookies, auth headers, CSRF tokens, and student IDs are strictly redacted before serialization.
* **Evidence-based classification**: No endpoint receives confidence $\ge 0.7$ without at least two independent pieces of corroborating evidence.

---

## Analysis Pipeline

```text
1. CAPTURE          → Intercept all HTTP requests/responses (with pre-navigation hooks)
       │
2. FILTER           → Remove static noise (.css, .js, .png, .woff2) & tracking domains
       │
3. DEDUPLICATE      → Collapse repeated hits by (method, normalized path, parameter keys)
       │
4. REQUEST ANALYSIS → Infer parameter schemas (student_id, csrf_token, timestamp, dynamic flags)
       │
5. RESPONSE ANALYSIS→ Parse HTML titles, headings (h1-h4), table headers (th), and keywords
       │
6. CLASSIFICATION   → Multi-signal scoring (category, purpose, confidence, evidence)
       │
7. REDACTION        → Strip credentials, tokens, cookies, and raw HTML dumps
       │
8. OUTPUT           → Write clean output/endpoints.json & raw captures/session_<id>/
```

---

## Key Capabilities

### 1. Request Schema Analysis
Infers parameter metadata and flags dynamic vs static fields:
* `csrf_token` / `session_id` / `timestamp` / `nonce` $\rightarrow$ `dynamic: true`
* `student_id` / `semester_id` / `course_id` / `boolean` / `integer` $\rightarrow$ `dynamic: false`

### 2. HTML & JSON Response Analysis
Decodes and inspects response payloads:
* Extracts `<title>` and `<h1>`-`<h4>` headings.
* Extracts `<th>` table headers (e.g. `Course Code`, `Total Classes`, `Percentage`, `Max Mark`).
* Extracts form field names (`<input>`, `<select>`, `<button>`).
* Extracts keyword tokens (e.g. `attendance`, `marks`, `timetable`, `credits`, `cgpa`).

### 3. Multi-Signal Evidence-Based Classification
Classifies endpoints into distinct categories (`authentication`, `navigation`, `data`, `unknown`) and granular purposes (`attendance`, `marks`, `timetable`, `courses`, `course_details`, `profile`, `exam_schedule`, `academic_history`, `feedback`, `dashboard`).

* **Scoring rule**: Single evidence signals are capped below $0.70$. Scores $\ge 0.70$ require $\ge 2$ independent signals (e.g. URL pattern + response headings).

### 4. Structural Deduplication
Generates endpoint signatures based on HTTP method, normalized path, and sorted parameter names—completely agnostic to transient dynamic values (CSRF tokens, epoch timestamps, session tokens).

### 5. Clean Specification vs Raw Captures
* **`output/endpoints.json`**: Clean, human-readable specification with parameter schemas, response analyses, categories, confidence, and evidence. Raw HTML response bodies are excluded.
* **`captures/session_<timestamp>/raw_exchanges.json`**: Complete raw request/response records for offline debugging.

### 6. Privacy & Strict Redaction
* Headers (`Cookie`, `Authorization`, `X-CSRF-Token`, etc.) are masked as `"[REDACTED]"`.
* Form data, JSON payloads, and query parameters containing credentials, OTPs, or student registration numbers are replaced with safe schema representations.

---

## Discovery Modes

### Automated Web Crawler Mode (Default)
```bash
vtop-discover
```
Log in manually once. The crawler automatically detects login, expands all sidebar menus and accordions, clicks through every portal section and inner tab, waits for network requests to settle, and compiles the catalog automatically.

### Guided Discovery Wizard
```bash
vtop-discover --guided
```
Step-by-step interactive CLI prompts you through opening specific sections sequentially:
1. `[1/7] Attendance`
2. `[2/7] Marks`
3. `[3/7] Timetable`
4. `[4/7] Courses & Registration`
5. `[5/7] Student Profile`
6. `[6/7] Examinations`
7. `[7/7] Academic History`

---

## Installation

```bash
cd vtop-endpoint-discovery
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
playwright install chromium
```

---

## Usage & CLI Options

```bash
# Run from root workspace
python discovery.py [OPTIONS]

# Or using the package entry point
vtop-discover [OPTIONS]
```

| Option | Description | Default |
| :--- | :--- | :--- |
| `-o, --output` | Path to save clean endpoint inventory JSON | `output/endpoint_inventory.json` |
| `--captures-dir` | Directory to save raw debugging captures | `captures/` |
| `--session` | Path to stored VTOP session JSON file | Auto-detects `.vtop-session/session.json` |
| `--url` | Starting VTOP URL | `https://vtop.vit.ac.in/vtop/open/page` |
| `--headed` | Run browser in visible headed mode | `True` |
| `--headless` | Run browser in background headless mode | `False` |
| `-a, --auto` | Enable automated safe crawler mode | `True` |
| `-g, --guided` | Run step-by-step guided discovery wizard | `False` |
| `--max-pages` | Maximum navigation sections to visit | `50` |
| `--max-actions` | Maximum click/selection actions | `100` |
| `--max-depth` | Maximum menu discovery depth | `50` |
| `--request-timeout` | Timeout per network/page action (seconds) | `4.0` |
| `-d, --diff OLD` | Compare two inventory JSON files | `None` |
| `-v, --debug` | Enable debug logging | `False` |

---

## Output Schema (`endpoint_inventory.json`)

```json
{
  "generated_at": "2026-09-12T19:40:00Z",
  "base_domains": [
    "https://vtop.vit.ac.in"
  ],
  "endpoints": {
    "POST_vtop_processviewstudentattendance": {
      "id": "POST_vtop_processviewstudentattendance",
      "name": "processViewStudentAttendance",
      "method": "POST",
      "path": "/vtop/processviewstudentattendance",
      "classification": "READ",
      "category": "data",
      "purpose": "attendance",
      "confidence": 0.95,
      "evidence": [
        "URL path contains 'attend'",
        "Request parameters contain academic query identifiers (semesterSubId/courseId)",
        "Response headings contain 'attendance summary'",
        "Table headers contain 'percentage'"
      ],
      "hit_count": 3,
      "first_seen": "2026-09-12T19:40:10Z",
      "last_seen": "2026-09-12T19:40:45Z",
      "request": {
        "parameters": {
          "authorizedID": {
            "location": "form",
            "examples": ["25BCE0001"],
            "type": "student_id",
            "dynamic": false,
            "required": true,
            "description": "Student registration identifier"
          },
          "semesterSubId": {
            "location": "form",
            "examples": ["VL20262705"],
            "type": "semester_id",
            "dynamic": false,
            "required": true,
            "description": "Semester or academic term identifier"
          },
          "_csrf": {
            "location": "query",
            "examples": [],
            "type": "csrf_token",
            "dynamic": true,
            "required": true,
            "description": "Anti-CSRF validation token"
          }
        },
        "headers": {
          "Host": "vtop.vit.ac.in",
          "Cookie": "[REDACTED]"
        }
      },
      "response": {
        "status": 200,
        "status_codes": [200],
        "content_type": "text/html;charset=UTF-8",
        "analysis": {
          "title": "VTOP - Student Attendance",
          "headings": ["ATTENDANCE SUMMARY", "Winter Semester 2026"],
          "table_headers": ["Course Code", "Course Title", "Total Classes", "Attended", "Percentage"],
          "form_fields": ["semesterSubId", "_csrf"],
          "keywords": ["attendance", "course details"],
          "produced_fields": {
            "semesterSubId": ["VL20262705", "VL20252601"]
          }
        }
      }
    }
  },
  "workflows": [
    {
      "name": "workflow_1",
      "steps": [
        "POST_vtop_academics_common_studentattendance",
        "POST_vtop_processviewstudentattendance"
      ],
      "dependencies": [
        {
          "parameter": "semesterSubId",
          "produced_by": "POST_vtop_academics_common_studentattendance",
          "consumed_by": "POST_vtop_processviewstudentattendance"
        }
      ]
    }
  ]
}
```

---

## Safety & Write Avoidance

The automated explorer adheres to strict safety boundaries to ensure student records and application states are never altered:
- **Keyword Filtering**: Buttons, links, and forms containing state-changing keywords (`hostel leave`, `apply leave`, `submit`, `register`, `withdraw`, `payment`, `confirm`, `cancel`, `delete`, `change course`) are blocked from automated execution.
- **Skipped Logging**: When an unsafe action is detected, the crawler outputs `[SKIP] Potential write operation: <target>` and classifies the route as `UNKNOWN_WRITE_OR_UNSAFE`.
- **Bounded Exploration**: Protects against cyclic navigations with configurable limits (`--max-pages`, `--max-actions`, `--max-depth`) and unique element/action caches.

---

## Catalog Diffing Utility

Compare newly discovered inventory JSON against a baseline:

```bash
vtop-discover --diff baseline_inventory.json -o output/endpoint_inventory.json
```

---

## Running Tests

Run the complete automated test suite (synthetic mock pipeline, redaction, request/response analyzers, workflow dependency detection, crawler safety filters):

```bash
cd vtop-endpoint-discovery
.venv/bin/pytest -v
```

---

## Disclaimer

This project is intended exclusively for educational, authorized, and personal academic interface development. It does not bypass authentication, circumvent security controls, or modify institutional records.

