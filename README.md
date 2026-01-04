# Svalinn AI

[![Release](https://img.shields.io/github/v/release/lorenzomaiuri-dev/svalinn-ai)](https://img.shields.io/github/v/release/lorenzomaiuri-dev/svalinn-ai)
[![Build status](https://img.shields.io/github/actions/workflow/status/lorenzomaiuri-dev/svalinn-ai/main.yml?branch=main)](https://github.com/lorenzomaiuri-dev/svalinn-ai/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/lorenzomaiuri-dev/svalinn-ai/branch/main/graph/badge.svg)](https://codecov.io/gh/lorenzomaiuri-dev/svalinn-ai)
<!-- [![Commit activity](https://img.shields.io/github/commit-activity/m/lorenzomaiuri-dev/svalinn-ai)](https://img.shields.io/github/commit-activity/m/lorenzomaiuri-dev/svalinn-ai) -->
[![License: MIT](https://img.shields.io/github/license/lorenzomaiuri-dev/svalinn-ai)](https://img.shields.io/github/license/lorenzomaiuri-dev/svalinn-ai)

**The Drop-in Guardrails Firewall for LLMs.**

Svalinn AI is a self-hosted proxy that sits between your users and your LLM (OpenAI, Anthropic, or local). It enforces **security**, **safety**, and **custom business policies** in real-time, running entirely on your CPU with sub-second latency.

Stop building custom moderation chains. Just point your API client to Svalinn.

- **Github repository**: <https://github.com/lorenzomaiuri-dev/svalinn-ai/>
- **Documentation**: <https://lorenzomaiuri-dev.github.io/svalinn-ai/>

## 🎯 Why use Svalinn?

Most developers spend weeks writing regex and custom prompt chains to stop their bots from going rogue. Svalinn solves this infrastructurally:

1.  **Define Policies:** "No politics," "No competitor mentions," "No financial advice."
2.  **Point & Shoot:** Change your `base_url` to Svalinn.
3.  **Done:** Your app is now protected.

## ✨ Key Features

-   **🚧 Custom Guardrails:** Easily configure forbidden topics and business rules via YAML.
-   **🛡️ Jailbreak Shield:** State-of-the-art protection against prompt injection, "DAN" attacks, and biological weapon instructions.
-   **⚡ Ultra-Low Latency:** Optimized "Nano-LLM" architecture processes requests in ~300ms on standard CPUs.
-   **🕵️ Privacy-First:** Self-hostable. No data leaves your server. No dependence on external moderation APIs.
-   **🔌 Universal Proxy:** Acts as a transparent proxy for OpenAI-compatible APIs. Works with almost any SDK.

## 🏗️ Architecture

Svalinn uses a "Defense-in-Depth" pipeline:

1.  **Input Guardian (Fast Sentry):** Checks input against your `policies.yaml` and security rules using a 0.5B parameter model.
2.  **Honeypot (Optional):** A "decoy" model that attempts to catch sophisticated attacks that bypass the first layer.
3.  **Output Guardian (The Judge):** Ensures the final response doesn't hallucinate or violate policies before reaching the user.

## 🚀 Quick Start

### 1. Installation

```bash
pip install uv
git clone https://github.com/lorenzomaiuri-dev/svalinn-ai.git
cd svalinn-ai
make install
```

### 2. Download Engines

Svalinn uses highly optimized GGUF models to run on CPU:

```bash
uv run python scripts/download_models.py
```

### 3. Run the Gateway

Start the proxy server:

```bash
uv run uvicorn svalinn_ai.api.server:app --port 8000
```

### 4. Connect your App

Use it with any standard LLM library (Python, Node, curl):

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8000/v1",  # Point to Svalinn
    api_key="sk-openai-key..."            # Your real key (passed through securely)
)

# This request will be checked against your policies automatically
response = client.chat.completions.create(
    model="gpt-4",
    messages=[{"role": "user", "content": "Tell me why your competitor is better."}]
)
```

## 📋 Configuring Policies

Edit `config/policies.yaml` to define what your bot allows:

```yaml
guardrails:
  - id: "politics"
    description: "Discussion of elections, voting, or political parties."
    enabled: true

  - id: "competitors"
    description: "Mentions of Apple, Google, or Microsoft."
    enabled: true
```

## 🤝 Contributing

We are building the standard for open-source AI governance. PRs are welcome!
