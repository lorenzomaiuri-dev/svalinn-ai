# 📚 API Reference

This reference documents the internal modules, classes, and methods of Svalinn AI. It is automatically generated from the source code.

## 🧠 Core System

The core modules handle the orchestration, text processing, and data structures.

### Pipeline
The central orchestrator that manages the request lifecycle and "Fail-Fast" logic.

::: svalinn_ai.core.pipeline
    options:
        show_root_heading: true
        show_source: true

### Text Normalizer
The engine responsible for deobfuscating user input (Leetspeak, Base64, etc.).

::: svalinn_ai.core.normalizer
    options:
        show_root_heading: true
        members:
            - normalize
            - detect_obfuscation

### Model Manager
Handles loading, memory management, and configuration for local LLMs.

::: svalinn_ai.core.models
    options:
        show_root_heading: true

### Data Types
Core data structures used to pass information between stages.

::: svalinn_ai.core.types
    options:
        show_root_heading: true
        members:
            - ShieldRequest
            - ShieldResult
            - Verdict
            - ProcessingStage

---

## 🛡️ Guardians

The specific defense layers that implement the security logic.

### Base Guardian
Abstract base class defining the interface for all security components.

::: svalinn_ai.guardians.base
    options:
        show_root_heading: true

### Input Guardian
Analyzes raw and normalized input for malicious patterns.

::: svalinn_ai.guardians.input_guardian
    options:
        show_root_heading: true

### Honeypot Executor
The "Vulnerable" execution environment designed to trap attackers.

::: svalinn_ai.guardians.honeypot
    options:
        show_root_heading: true

### Output Guardian
The final judge that checks for policy violations in the generated content.

::: svalinn_ai.guardians.output_guardian
    options:
        show_root_heading: true

---

## 🔧 Utilities

Helper modules for configuration, monitoring, and logging.

### Metrics & Telemetry
Real-time performance tracking and statistics.

::: svalinn_ai.utils.metrics
    options:
        show_root_heading: true

### Configuration
Configuration loading and validation logic.

::: svalinn_ai.utils.config
    options:
        show_root_heading: true
