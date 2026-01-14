# ACE Platform: Enterprise Reasoning Engine

The **ACE Platform** is a generalized framework for **Agentic Context Engineering**. It decouples the core "Generate-Reflect-Curate" cognitive loop from specific domain implementations, allowing teams to build self-correcting agents for any task (OpenAPI, Terraform, SQL, etc.).

## Architecture

The platform consists of two main layers:

### 1. The Engine (`/engine`)
The reusable core that handles:
*   **The Loop**: Managing Epochs and Convergence.
*   **Memory**: Vector Store interactions (supporting Hybrid Search & Cross-Encoder Reranking) and **Persistent Context Playbook** (long-term learning).
*   **LLM Orchestration**: Centralized client for AI models.

### 2. Plugins (`/plugins`)
Domain-specific "cartridges" that define:
*   **Data Sources**: How to read input (PDFs, Git, DBs).
*   **Prompts**: Valid System Instructions for the Generator.
*   **Validation Rules**: Logic for the Reflector (Style Guides, Linters).

## Directory Structure

```
ace_platform/
├── engine/              # UNIVERSAL CORE
│   ├── loop.py          # The main Agent Loop class
│   ├── memory.py        # Vector Store & Curator Logic
│   └── llm.py           # Model Wrappers
│
├── plugins/             # DOMAIN IMPLEMENTATIONS
│   └── openapi_gen/     # Example: The Original OAS Agent
│       ├── config.yaml  # Prompts & Rules
│       └── adapter.py   # PDF Reading Logic
│
└── main.py              # CLI Entry Point
```

## Getting Started

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Run a Plugin**:
    ```bash
    python main.py --plugin openapi_gen --input docs/product_spec.pdf
    ```
