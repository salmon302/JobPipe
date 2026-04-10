

# Software Requirements Specification (SRS)
**Project:** JobPipe (Automated AI Job Search & Resume Pipeline)
**Version:** 1.0

---

## 1. Introduction

### 1.1 Purpose
This document specifies the requirements for a semi-automated system designed to scrape, score, and prioritize job postings from platforms like HiringCafe, Wellfound, and Built In. Additionally, it outlines the requirements for an integrated Model Context Protocol (MCP) server that interfaces with the Claude Desktop application to generate highly targeted, 1-page LaTeX-to-PDF resumes based on a master Markdown CV.

### 1.2 Scope
The system will run locally as a background daemon (Windows). It is composed of two primary subsystems:
1.  **The Aggregator:** A headless browser scraper and scoring engine that ranks jobs based on vector similarity and heuristic rules (e.g., Years of Experience, Recency).
2.  **The Resume Generator:** A local MCP server that allows Claude Desktop to read a Master CV, ingest a target job description, propose LaTeX modifications, and compile a final PDF upon human approval.

---

## 2. System Architecture

* **Ingestion Layer:** Headless browser automation (Playwright/Selenium) configured with rotating user agents and scheduled execution to bypass basic anti-bot measures.
* **Storage Layer:** Local SQLite database to track processed Job IDs, prevent duplicate alerts, and store job metadata.
* **Analysis Layer:** Local or API-based embedding model (e.g., `text-embedding-3-small`) to generate vectors for job descriptions and compare them via cosine similarity against the user's base CV vector.
* **Notification Layer:** Native OS desktop notifications to alert the user of high-priority matches.
* **Generation Layer (MCP):** A local Python MCP server connected to Claude Desktop, providing file read/write access to a designated resume directory.
* **Compilation Layer:** Local TeX distribution (e.g., TeX Live) to compile the LLM-generated `.tex` files into PDFs using a provided `.tex` template.

---

## 3. Functional Requirements

### 3.1 Data Ingestion (The Scraper)
* **REQ-1.1:** The system shall execute headless browsing sessions based on a configurable cron schedule or preset interval.
* **REQ-1.2:** The system shall handle basic account authentication for target platforms (HiringCafe, Wellfound, Built In) where required, excluding those with mandatory 2FA.
* **REQ-1.3:** The system shall parse dynamic, client-side rendered DOM elements to extract: Job Title, Company, URL, Posting Date, and raw Job Description text.
* **REQ-1.4:** The system shall store extracted data in the SQLite database and flag jobs that have already been processed to avoid redundant scoring.

### 3.2 The Prioritization Engine
* **REQ-2.1:** The system shall implement an **Algorithmic Pre-Filter** using regex and keyword matching to identify "Critical Skills" (e.g., specific languages or frameworks) before API calls.
* **REQ-2.2:** The system shall calculate an **Attainability Penalty** based on the following heuristic:
    * `0-1 years`: Entry-level (no penalty for new grads).
    * `2-3 years`: Possible entry-level (minor penalty).
    * `3-5 years`: True reach (significant penalty).
    * `5+ years`: Senior (maximum penalty/discard).
* **REQ-2.3:** The system shall apply a **Recency Decay** multiplier:
    * Remote Jobs: Penalize significantly if >24 hours old.
    * Local Jobs: Linear decay over 7 days (less aggressive for specialized roles).
* **REQ-2.4:** The system shall generate a vector embedding of the job description only for candidates passing the pre-filter, calculating Cosine Similarity against the user's Master CV.
* **REQ-3.5:** The system shall calculate the `Total Match Score` = `(Relevance * 0.5) + (Attainability * 0.3) + (Recency * 0.2)`.

### 3.3 Notification System
* **REQ-3.1:** The system shall trigger a native Windows Toast notification if a job's `Total Match Score` exceeds a user-defined threshold (e.g., >85%).
* **REQ-3.2:** The notification shall include the Job Title, Company, Match Score, and a clickable hyperlink to the original posting.

### 3.4 MCP Server & Resume Generation
* **REQ-4.1:** The MCP server shall expose the local Master CV (`Master_CV.md`) and the queued Job Description (`Job_Description.md`) as readable resources to Claude Desktop.
* **REQ-4.2:** The system shall provide a pre-defined "Skill" or prompt template to instruct Claude to select relevant bullet points and format them into a strict LaTeX template.
* **REQ-4.3:** The MCP server shall require human approval (via Claude Desktop's diff review UI) before executing a write operation to save the targeted `.tex` file to the local disk.
* **REQ-4.4:** Upon successful file write, the system shall trigger a local `pdflatex` (or equivalent) command to compile the file into a `.pdf`.

---

## 4. Non-Functional Requirements

* **Execution Environment:** The system must run entirely locally (with the exception of API calls for embeddings and Claude).
* **Rate Limiting:** The scraper must implement randomized delays (jitter) between HTTP requests and page navigations to prevent IP bans from target websites.
* **Idempotency:** The compilation script must be able to overwrite previous `.tex` and `.pdf` files cleanly without locking errors if the user requests an iterative revision from Claude.
* **Data Structure:** The Master CV must be maintained in structured Markdown to ensure high parsing accuracy by the LLM.

---

## 5. Data Dictionary (Core Entities)

**Table: `jobs`**
* `id` (Primary Key, String): Unique identifier from the source platform.
* `platform` (String): Source of the job (e.g., "HiringCafe").
* `title` (String): Job title.
* `company` (String): Company name.
* `url` (String): Link to the application.
* `description` (Text): Raw text of the job description.
* `date_posted` (DateTime): Extracted posting date.
* `match_score` (Float): Computed similarity and viability score.
* `status` (String): e.g., "Queued", "Notified", "Applied", "Rejected".

**File: `Master_CV.md`**
* Contains all professional experience, education, and skills.
* Structured with distinct tags (e.g., `[Backend]`, `[Data Engineering]`) to assist the LLM in targeted filtering.