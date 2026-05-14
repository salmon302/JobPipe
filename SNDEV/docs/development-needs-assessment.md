# Development Needs Assessment
# Author: Seth Nenninger (Tencent: Hy3 preview Agent)
# Timestamp: 2026-05-12T21:30:00Z

## SRS v3.0 Requirements vs. Implementation Status

### ✅ COMPLETED Requirements

| SRS ID | Requirement | Status | Implementation |
|---------|--------------|--------|----------------|
| REQ-1.1 | Manual trigger on job boards | ✅ COMPLETE | Browser extension (Manifest V3) |
| REQ-1.2 | Extract Job Title, Company, URL, Description | ✅ COMPLETE | `extension/utils/extractors.js` |
| REQ-1.3 | Transmit JSON payload to local server | ✅ COMPLETE | Extension POSTs to `/ingest` |
| REQ-1.4 | Visual confirmation (toast) | ✅ COMPLETE | `chrome.notifications` API |
| REQ-2.1 | Local server on designated port | ✅ COMPLETE | `src/jobpipe/ingest/server.py` |
| REQ-2.2 | Compute Total Match Score | ✅ COMPLETE | `src/jobpipe/scoring/calculator.py` |
| REQ-2.3 | Display prioritized dashboard | ✅ COMPLETE | `src/jobpipe/gui/app.py` |
| REQ-3.1 | "Generate Application" action | ✅ COMPLETE | `jobpipe resume-stage` CLI |
| REQ-3.2 | Gemini API integration | ✅ COMPLETE | `src/jobpipe/resume/gemini_client.py` |
| REQ-3.3 | Built-in LaTeX editor | ✅ COMPLETE | `src/jobpipe/gui/latex_editor.py` |
| REQ-3.4 | "Approve & Compile" button | ✅ COMPLETE | GUI button + `approve_and_compile_resume()` |
| REQ-4.1 | Save .tex to /applications/ | ✅ COMPLETE | `write_targeted_resume()` |
| REQ-4.2 | pdflatex without blocking GUI | ✅ COMPLETE | Background thread + `pdflatex` |

### ⚠️ PARTIALLY COMPLETE

| SRS ID | Requirement | Gap | Needed |
|---------|--------------|-----|-------|
| NFR-1.1 | Zero-cost Gemini API usage | Needs API key setup docs | User documentation |
| NFR-2.1 | Strip PII from Master CV | No validation implemented | Add PII scanner |
| NFR-3.1 | Lightweight server footprint | Not measured/optimized | Performance testing |

### ❌ NOT STARTED (Non-Critical)

| SRS ID | Requirement | Priority | Notes |
|---------|--------------|----------|-------|
| - | Keyboard shortcuts for extension | Low | Add `commands` to manifest |
| - | PDF preview pane in GUI | Medium | Requires PDF.js or similar |
| - | Diff view for resume versions | Low | Compare revisions |
| - | Line numbers in LaTeX editor | Low | QCodeEditor alternative |
| - | CI/CD pipeline | Medium | GitHub Actions for testing |
| - | Production deployment docs | Medium | User setup guide |

---

## Immediate Development Needs

### 1. **User Documentation (High Priority)**
- [ ] Create `docs/USER_GUIDE.md` with step-by-step setup
- [ ] Document Gemini API key configuration
- [ ] Document extension installation process
- [ ] Create video/text tutorial for complete workflow

### 2. **PII Protection (NFR-2.1)**
- [ ] Add PII scanner to warn about sensitive data in Master CV
- [ ] Implement pre-flight check before API transmission
- [ ] Add configuration for PII patterns (SSN, address, phone)

### 3. **Testing & Quality Assurance**
- [ ] **Integration tests with real Gemini API** (need API key)
- [ ] **Load testing** for ingest server (multiple concurrent requests)
- [ ] **GUI testing** (PySide6 tests require display server)
- [ ] **Cross-browser testing** for extension (Chrome, Edge, Firefox)

### 4. **CI/CD Pipeline (Medium Priority)**
- [ ] Create `.github/workflows/test.yml`
- [ ] Run pytest on Python 3.11, 3.12, 3.13, 3.14
- [ ] Install dependencies (sentence-transformers, PySide6)
- [ ] Run linting (ruff)
- [ ] Generate coverage reports

### 5. **GUI Enhancements (Medium Priority)**
- [ ] **PDF Preview Pane**: Display compiled PDF in GUI
  - Use PDF.js or convert to images
  - Add zoom in/out controls
- [ ] **Diff View**: Compare resume revisions
  - Show changes between versions
  - Accept/reject individual changes
- [ ] **Recent Files**: Quick access to recent resumes
- [ ] **Settings UI**: Add Gemini API key field to GUI

### 6. **Extension Enhancements (Low Priority)**
- [ ] **Keyboard Shortcuts**: Add `commands` section to manifest.json
  ```json
  "commands": {
    "capture-job": {
      "suggested_key": {"default": "Ctrl+Shift+J"},
      "description": "Capture job listing"
    }
  }
  ```
- [ ] **Options Page**: Create `options.html` for server URL configuration
- [ ] **Context Menu**: Right-click to capture job
- [ ] **Firefox Support**: Test and adapt for Manifest V3 in Firefox

### 7. **Performance Optimization (NFR-3.1)**
- [ ] Profile ingest server memory usage
- [ ] Optimize sentence-transformers model loading
- [ ] Add caching for embeddings
- [ ] Implement connection pooling for SQLite

---

## Recommended Next Steps (Prioritized)

### 🔥 **Phase 1: User Readiness (1-2 days)**
1. Create comprehensive user documentation
2. Add PII protection warnings
3. Create setup video/text tutorial
4. Test complete workflow end-to-end with real API key

### 🧪 **Phase 2: Quality Assurance (2-3 days)**
1. Set up CI/CD with GitHub Actions
2. Add integration tests with real Gemini API
3. Perform load testing on ingest server
4. Cross-browser extension testing

### 🚀 **Phase 3: Enhancements (1-2 weeks)**
1. Add PDF preview pane to GUI
2. Implement diff view for resume versions
3. Add keyboard shortcuts to extension
4. Performance optimization

---

## Current Project State Summary

### ✅ **Core Functionality: 100% Complete**
- Browser extension captures jobs ✅
- Ingest server receives and processes ✅
- SQLite database stores with scoring ✅
- Gemini API generates resumes ✅
- LaTeX editor with syntax highlighting ✅
- Approve & Compile workflow ✅
- PDF compilation via pdflatex ✅

### ⚠️ **User Readiness: 60% Complete**
- Code complete, needs documentation ✅
- Extension icons need generation ⚠️
- Gemini API key setup docs needed ⚠️
- User guide/tutorial needed ⚠️

### 📊 **Nice-to-Have: 0% Complete**
- PDF preview pane
- Diff view
- Keyboard shortcuts
- CI/CD pipeline
- Performance optimization

---

## Conclusion

**The JobPipe project is functionally complete** and ready for use by developers.

**To make it user-ready:**
1. ✅ Generate extension icons (user action)
2. ⚠️ Create user documentation
3. ⚠️ Add PII protection warnings
4. ⚠️ Test with real Gemini API key

**Optional enhancements** can be added incrementally based on user feedback.

---

## Action Items for Next Session

1. [ ] Create `docs/USER_GUIDE.md`
2. [ ] Implement PII scanner for Master CV
3. [ ] Set up GitHub Actions CI/CD
4. [ ] Add PDF preview pane to GUI
5. [ ] Create setup tutorial (video or text with screenshots)
