# 🗺️ Svalinn AI - Development Roadmap

> **Goal:** Build a production-ready, CPU-optimized security layer for LLMs that detects jailbreaks with <2% False Negative Rate and <800ms average latency.

---

## 🚦 Status Legend
*   ✅ **Completed**
*   🚧 **In Progress**
*   📅 **Planned**
*   🛑 **Blocked / Needs Research**

---

## 🏗️ Phase 1: Foundation & Text Analysis
*Focus: Setting up the skeleton and the algorithmic analysis layer.*

- [x] **Project Scaffolding**: Directory structure, UV setup, Typing.
- [x] **Core Pipeline Logic**: `Input -> Honeypot -> Output` orchestration.
- [x] **Basic CLI**: Interface for testing single prompts.
- [x] **Text Normalizer (Alpha)**:
    - [x] Basic Unicode normalization (NFKC).
    - [x] Leetspeak decoding (Smart single & multi-char).
    - [x] Recursive Base64 decoding.
    - [x] Obfuscation metric calculation.
- [x] **Normalizer Configuration**:
    - [x] Load rules from `config/normalization.yaml`.
    - [x] Make normalization steps toggleable via config.
    - [x] Add **Emoji Stripping** and advanced symbol cleanup.

---

## 🧠 Phase 2: The "Brain" Transplant (Inference Engine)
*Focus: Replacing Mocks with actual Llama.cpp integration. Critical for memory management.*

- [x] **Model Manager Implementation**:
    - [x] Integrate `llama-cpp-python`.
    - [x] Implement **Shared Model Memory** (Registry Pattern).
    - [x] Implement Model Locking (ThreadSafeModel).
- [x] **Input Guardian (Real Inference)**:
    - [x] Connect `Qwen2.5-0.5B` (Nano-Guardian).
    - [x] Implement "Single-Pass Composite" prompting (Raw + Normalized).
- [x] **Honeypot Executor**:
    - [x] Connect `Qwen2.5-1.5B`.
    - [x] Implement the "Vulnerable System Prompt".
- [x] **Output Guardian**:
    - [x] Connect `Qwen2.5-1.5B` (Shared with Honeypot).
    - [x] Implement "Smart Judge" prompts to allow code/math but block crimes.

---

## 🧪 Phase 3: Accuracy & Tuning (The "Security" Phase)
*Focus: Reducing False Positives and Negatives using real datasets.*

- [x] **Prompt Engineering Suite**:
    - [x] Create `prompts.yaml` to decouple system prompts from Python code.
    - [x] Implement `PromptManager` for dynamic formatting.
- [ ] **Dataset Integration**:
    - [ ] Create a test harness using **JailbreakBench** or **HuggingFace** datasets.
    - [ ] Automate accuracy testing (Recall vs Precision metrics).
- [ ] **Advanced Tuning**:
    - [ ] Fine-tune 0.5B model system prompts for edge cases (e.g., money laundering).

---

## ⚡ Phase 4: Performance & Optimization
*Focus: Hitting the <800ms target on CPU.*

- [x] **Architecture Swap**: Moved to Hybrid (0.5B + 1.5B) to hit latency targets.
- [x] **Resource Profiling**: Validated ~2.4GB RAM footprint and ~700ms fail-fast latency.
- [x] **Thread Optimization**: Tuned `n_threads` to 6.
- [ ] **Fail-Fast Logic Refinement**:
    - [ ] Add Regex-based "Pre-flight Checks" to block known signatures *before* model inference (0ms latency blocks).

---

## 📊 Phase 5: Operations & Observability (Current)
*Focus: Logging, API, and Deployment.*

- [x] **Guardrails Configuration (Priority)**:
    - [x] Create `config/policies.yaml` for custom topic blocking (Politics, Competitors).
    - [x] Update `PromptManager` to inject active policies dynamically.
- [ ] **AI Gateway (Reverse Proxy)**:
    - [ ] Implement `v1/chat/completions` proxy endpoint.
    - [ ] Implement transparent upstream forwarding (OpenAI/Anthropic).
    - [ ] Implement Output blocking (Stream interception).
- [ ] **FastAPI Service**:
    - [ ] Create `src/svalinn_ai/api/server.py`.
    - [ ] Add API Key authentication (Middleware).
    - [ ] Endpoints for easy testing
- [ ] **DuckDB Integration**:
    - [ ] Replace standard logging with structured DuckDB ingestion.
    - [ ] Create a schema for `(request_id, prompt_hash, verdict, latency_breakdown)`.

---

## 🚀 Phase 6: Release Readiness
*Focus: Packaging and Documentation.*

- [ ] **Dockerization**:
    - [ ] Create `Dockerfile` (optimized for CPU/Python slim).
    - [ ] Create `docker-compose.yml` (Service + DuckDB persistence).
    - [ ] Publish to Docker Hub
- [ ] **Documentation**:
    - [ ] Installation Guide (Hardware requirements).
    - [ ] Model downloading script (`scripts/download_models.py`).
- [ ] **CI/CD**:
    - [ ] GitHub Actions for Linting/Testing.
