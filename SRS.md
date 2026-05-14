

   # Software Requirements Specification (SRS)

**Project:** AI-Assisted Job Harvester & Resume Pipeline
**Version:** 3.0

---

## 1. Introduction

### 1.1 Purpose

This document specifies the requirements for a semi-automated job search and application generation system. The system shifts away from fully automated scraping to a "Human-in-the-Loop Browsing" model, utilizing a browser extension to capture jobs manually selected by the user. It integrates directly with the Gemini API to score jobs and generate tailored LaTeX resumes, leveraging a local GUI for review and compilation.

### 1.2 Scope

The system consists of two primary subsystems operating in tandem:

1. **The Browser Extension (Harvester):** A lightweight extension (Manifest V3) that extracts job data from actively browsed pages and transmits it locally.
2. **The Local GUI (Command Center):** A desktop or local web application that receives job data, scores matches, interfaces with the Gemini API (via a zero-cost Google AI Studio key) to generate targeted resumes, and provides a text editor for manual review before compiling to PDF.

---

## 2. System Architecture

* **Ingestion Layer:** Browser extension running on the user's active browser, extracting fully rendered DOM elements to bypass anti-bot protections.
* **Communication Layer:** Local HTTP server embedded in the GUI to receive JSON payloads from the extension.
* **Storage Layer:** Local SQLite database to track processed Job IDs, scores, and application statuses.
* **Analysis & Generation Layer:** Direct integration with the Gemini API. Uses a fast model for scoring (e.g., Gemini 1.5 Flash) and a highly capable model for text generation (Gemini 3.1 Pro) via a free-tier Google AI Studio key.
* **Review Layer:** A built-in code editor UI within the local GUI for reviewing and modifying the LLM-generated LaTeX code.
* **Compilation Layer:** Local TeX distribution (e.g., TeX Live or MiKTeX) invoked via background shell commands to compile the approved `.tex` files into `.pdf`.

---

## 3. Functional Requirements

### 3.1 Data Ingestion (Browser Extension)

* **REQ-1.1:** The extension shall provide a manual trigger (UI button or keyboard shortcut) on supported job boards (e.g., HiringCafe, LinkedIn, Built In).
* **REQ-1.2:** Upon trigger, the extension shall extract the Job Title, Company, URL, and raw Job Description text from the active tab's DOM.
* **REQ-1.3:** The extension shall transmit the extracted data as a JSON payload to the local GUI application via an HTTP POST request.
* **REQ-1.4:** The extension shall display a brief visual confirmation (toast notification) upon successful transmission.

### 3.2 The GUI Dashboard & Scoring

* **REQ-2.1:** The desktop GUI shall run a local server listening on a designated port to receive incoming job payloads from the extension.
* **REQ-2.2:** Upon receipt, the system shall compute a `Total Match Score` utilizing vector similarity (CV vs. Job Description) and heuristic penalties (e.g., Attainability based on Years of Experience).
* **REQ-2.3:** The GUI shall display a prioritized, sortable dashboard of all ingested jobs, highlighting the highest-scoring matches.

### 3.3 Resume Generation & Review

* **REQ-3.1:** The GUI shall feature a "Generate Application" action for each job in the queue.
* **REQ-3.2:** Triggering this action shall package the user's base `Master_CV.md`, the `Job_Description.md`, and a predefined LaTeX template into a prompt, sending it directly to the Gemini API.
* **REQ-3.3:** The GUI shall render the API's response within a built-in text/code editor pane, allowing the user to manually review, edit, and correct the generated LaTeX.
* **REQ-3.4:** The code editor shall feature an "Approve & Compile" button to finalize the review process.

### 3.4 Compilation

* **REQ-4.1:** Upon clicking "Approve & Compile", the system shall save the contents of the text editor to the local disk as a targeted `.tex` file (e.g., `/applications/Company_Role/resume.tex`).
* **REQ-4.2:** The system shall execute a local `pdflatex` (or equivalent) command to compile the `.tex` file into a `.pdf` without blocking the main GUI thread.

---

## 4. Non-Functional Requirements

### 4.1 Cost Constraints

* **NFR-1.1:** The system shall strictly utilize a Google AI Studio API key without an attached billing account to ensure zero out-of-pocket costs, relying entirely on subscriber/free-tier rate limits.

### 4.2 Data Privacy

* **NFR-2.1:** The base `Master_CV.md` must be stripped of highly sensitive Personally Identifiable Information (PII) prior to API transmission, as free-tier API usage is subject to logging and model training by the provider.

### 4.3 Performance & Reliability

* **NFR-3.1:** The local server must maintain a lightweight footprint to run persistently in the background during active browsing sessions.
* **NFR-3.2:** The compilation script must cleanly overwrite existing `.tex` and `.pdf` files to support iterative generation without file-locking errors.

---

## 5. Data Dictionary

**Entity: `Job**`

* `id` (String): Unique identifier (hash of URL or source ID).
* `platform` (String): Source website (e.g., "HiringCafe").
* `title` (String): Extracted job title.
* `company` (String): Extracted company name.
* `url` (String): Hyperlink to the original posting.
* `description` (Text): Raw job description text.
* `match_score` (Float): Computed similarity and attainability score.
* `status` (String): Current pipeline state ("Queued", "Generated", "Applied", "Archived").

**Entity: `Master_CV.md**`

* **Structure:** Markdown document containing the user's complete professional history, education, and skills.
* **Formatting:** Utilizes distinct tags (e.g., `[Frontend]`, `[Leadership]`) to guide the LLM's filtering process during generation. Ensure sensitive data (exact address, SSN) is omitted.

Gemini Info:

API Key (Example)

Name
Gemini API Key
Project name
projects/95707303401
Project number
95707303401
curl "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent" \
  -H 'Content-Type: application/json' \
  -H 'X-goog-api-key: ' \
  -X POST \
  -d '{
    "contents": [
      {
        "parts": [
          {
            "text": "Explain how AI works in a few words"
          }
        ]
      }
    ]
  }'
