# ACE: Agentic Context Engineering for OpenAPI Generation

This project implements an **Agentic Context Engineering (ACE)** system designed to autonomously generate high-quality OpenAPI Specifications (OAS 3.0) from unstructured Product Requirements and Style Guides.

## Core Architecture

The system operates on a **Generate-Reflect-Curate** loop, evolving its understanding of the task through iterations.

### 1. The RAG Engine (`GoogleVectorStore`)
This module is designed as a **Production-Grade Abstraction** over Google Cloud Vertex AI Vector Search, with a seamless local fallback for development.

*   **Google Vertex AI Integration**:
    *   **Embeddings**: Uses `text-embedding-004` via the Vertex AI SDK to generate 768-dimensional vectors.
    *   **Vector Search**: The code includes the scaffolding to connect to a deployed `MatchingEngineIndexEndpoint` for massive-scale, low-latency approximate nearest neighbor (ANN) search in the cloud.
*   **Local Fallback (The "Simulator")**:
    *   To allow for fast iteration without deploying costly cloud indexes, the system automatically falls back to a **Local Vector Store**.
    *   **Mechanism**: It stores embeddings in an in-memory list and performs **Brute-Force Exact Search** (`O(N)`) using `scikit-learn`'s Cosine Similarity.
    *   **Performance**: For datasets < 10,000 chunks (like most Product Specs), this is faster (<50ms) and more accurate than ANN. For >100k chunks, one must switch to the Cloud Index to avoid latency.
    *   **Persistence**: Data is pickled to `vector_store.pkl`, allowing the "database" to survive between script runs.
*   **Hybrid Search Implementation**:
    *   **Layer 1 (Metadata)**: Hard filters exclude irrelevant documents (e.g., "Only look at `product_spec`").
    *   **Layer 2 (Vector)**: Semantic search finds the most relevant content within that subset.

### 2. The PDF Pipeline & Chunking Design (`PDFChunker`)
We employ a **Multimodal, Context-Preserving Chunking Strategy** to handle complex documents.

*   **Text Processing**:
    *   **Library**: `pypdf` is used for raw extraction.
    *   **Sliding Window**: We use a chunk size of **1500 characters** with a **200-character overlap**.
        *   *Why?* Product specs often have sentences or logical clauses that span page or paragraph boundaries. Overlap ensures no crucial context is "cut in half" at the edge of a chunk.
*   **Multimodal (Image) Processing**:
    *   Standard RAG fails on diagrams (e.g., architecture flowcharts).
    *   **Visual Extraction**: The chunker extracts every image found in the PDF.
    *   **AI Captioning**: Each image is sent to **Gemini Pro Vision**, which generates a detailed textual description of the diagram.
    *   **Unified Embedding**: This caption is embedded just like normal text. If a user searches for "payment flow," the system can find the *description* of the payment flow diagram and retrieve it.

---

## Key Strategies & Workflows

### A. Iterative Feature Discovery (The "Deep Dive")
Instead of a single RAG call, the Generator employs a **Two-Pass Discovery Mechanism** to ensure comprehensive coverage:

1.  **Pass 1: Broad Feature Discovery**
    *   The Agent searches for "Table of Contents", "System Overview", and "Capabilities" to understand the *scope* of the product.
    *   It asks the LLM to extract a list of core **Feature Nouns** (e.g., "Users, Orders, Payments") from this high-level view.

2.  **Pass 2: Targeted Deep Dive**
    *   For *each* identified feature, the Agent performs specific RAG queries:
        *   `"{Feature} API endpoints"`
        *   `"{Feature} data model"`
        *   `"{Feature} requirements"`
    *   **High-Volume Retrieval**: It uses a massive retrieval window (`k=100`) to scan hundreds of pages, filtering strictly for the requested feature.
    *   **Context Aggregation**: All retrieved segments are compiled into a structured `Detailed Context` block.

3.  **Pass 3: Style Guide Enforcement**
    *   The Agent retrieves **ALL** available style guide rules via metadata filtering (`get_all_by_metadata`). This ensures no rule is left behind due to search relevance cutoffs.

### B. The Context Playbook (Dynamic Memory)
The Agent maintains a `context_playbook`—a mutable list of guidelines that evolves over time.
*   **Initial State**: Standard REST/YAML rules.
*   **Evolution**: After every epoch, the **Curator** analyzes the **Reflector's** critique and adds new rules to the playbook (e.g., "- Always return 404 for GET /id").
*   **Deduplication**: New rules are embedding-matched against existing ones to prevent bloat.

### C. The Epoch: A Self-Improvement Cycle
An "Epoch" represents one full pass of the Agent trying to build the perfect spec. We employ a **Quantitative Convergence** strategy:
*   **Hard Cap**: The system runs for a maximum of `N` epochs (default: 3) to prevent infinite loops.
*   **Early Stopping**: If the `Critique Length` (amount of feedback) drops by **less than 5%** between epochs, we assume diminishing returns and stop early.


**Step 1: Generate (The Synthesizer)**
*   **Semantic Translation**: The Generator performs deep semantic analysis to translate *unstructured product intent* into *structured technical specifications*.
*   **Strategic Scoping**: It acts as an Enterprise Architect, filtering out "Shared Services" (Auth, Keys, Onboarding) that typically belong to platform-level APIs, focusing strictly on the product's core domain value (e.g., "Inventory" vs "Login").
*   It resolves ambiguities in the Product Spec by correlating scattered requirements.

**Step 2: Reflect (The "Semantic Linter")**
*   **Beyond Syntax**: This is not just a syntax checker. It performs **Semantic Compliance Checking**.
*   It understands the *intent* of a Style Guide rule (e.g., "Error messages must be helpful") and judges the *meaning* of the generated API's error responses.
*   It detects subtle issues like "semantic versioning violations" or "inconsistent naming patterns" that a standard linter would miss.

**Step 3: Curate (The Learning)**
*   The **Curator** reads the Critique.
*   It asks: *"What rule did we forget?"*
*   It updates the `Context Playbook` with a new, imperative rule (e.g., " - GET requests MUST return 200 OK, never 201.").
**Result**: The next Epoch starts with this new rule in memory, guaranteed not to make the same mistake again.

### D. Hallucination Mitigation Strategies
We employ several architectural pillars to prevent the model from "inventing" features:

1.  **Strict Grounding (The "Deep Dive")**:
    *   We do not ask the LLM to "imagine" an API.
    *   The **Feature Discovery** phase identifies concrete topics (e.g., "Payments").
    *   The **Deep Dive** retrieves up to **100 chunks** of specific evidence concerning that topic.
    *   If no evidence is found for a feature, the RAG returns empty context, forcing the LLM to fall back to generic placeholders rather than hallucinating details.

2.  **Negative Constraints**:
    *   The Prompt explicitly instructs: *"If information is missing, use standard industry placeholders...".*
    *   This "Escape Hatch" is critical. It gives the model permission *not* to know, reducing the pressure to confabulate.

3.  **Structural Validation (The Reflector)**:
    *   While the Reflector focuses on Style, it acts as a strong filter against *Protocol Hallucinations* (e.g., using non-existent HTTP verbs or status codes).


---

## File Structure

*   `ace_agent.py`: Main entry point and orchestrator class (`ACEAgent`).
*   `utils/vector_store.py`: Abstraction over Vertex AI Embeddings and local storage.
*   `utils/chunker.py`: Logic for PDF parsing and Image Captioning.
*   `docs/`: Input PDFs (`product_spec.pdf`, `style_guide.pdf`).
*   `generated_openapi.yaml`: Deeply iteratively generated output.
*   `context_playbook.md`: Persisted memory of learned rules.

## API Reference: `ACEAgent` Class

### `__init__(self, model_name, mock=False)`
Initializes the agent, sets up the Vertex AI `GenerativeModel` (Gemini) and the `GoogleVectorStore`.
*   `mock` flag allows for unit testing without incurring LLM costs.

### `build_knowledge_base(self, product_spec_path, style_guide_path)`
Orchestrates the ingestion pipeline:
1.  Checks for a local `vector_store.pkl` cache.
2.  If missing, invokes `PDFChunker` to extract text and caption images.
3.  Tags chunks with `type='product_spec'` or `type='style_guide'`.
4.  Ingests them into the Vector Store and saves the cache.

### `generator(self, context_playbook)`
The core creative engine.
*   **Methodology**: Executes the **Two-Pass Discovery** strategy (Broad Search -> Deep Dive).
*   **Optimization**: Retrieves all Style Guide rules proactively.
*   **Output**: Returns a tuple of `(oas_yaml_string, feature_location_map)`.

### `reflector(self, candidate_oas)`
The critical feedback loop.
*   **Completeness Audit**: Re-scans the Product Spec high-level features and checks if the OAS is missing any core endpoints (e.g., "Product Spec mentions 'Invoices' but OAS has no `/invoices` path").
*   **Global Review**: Retrieves broad governance rules and audits the OAS `info`, `servers`, and `security` objects.
*   **Per-Endpoint Review**: Iterates through every path/verb in the OAS.
    *   Retrieves specific rules for naming, status codes, and errors.
    *   Asks the LLM to critique *only* that specific endpoint against the rules.
*   **Output**: A clean string of "NO_ISSUES" or a bulleted list of violations.

### `curator(self, current_playbook, critique)`
The memory manager.
*   **Input**: The previous playbook and the latest specific critique.
*   **Logic**: Asks the LLM to generalize the specific critique into a universal rule.
*   **Dedup Engine**: Embeds the new rule and checks cosine similarity against existing rules (>0.85 threshold) to prevent duplicates.
*   **Output**: The updated, deduplicated Playbook string.

### `run(self, ...)`
The main entry point that executes the `Generative -> Reflective -> Curative` loop for `N` epochs.

## API Reference: Utilities

### `utils.chunker.PDFChunker`
Responsible for converting PDFs into RAG-ready text chunks.

*   **`__init__(chunk_size=1500, overlap=200, image_model=None)`**: Configures the sliding window. If `image_model` (Gemini) is provided, it enables multimodal processing.
*   **`extract_text_with_metadata(pdf_path)`**:
    1.  Iterates through each page of the PDF.
    2.  **Text**: Extracts raw text using `pypdf`.
    3.  **Images**: If an image is found, sends it to Gemini which returns a textual description (e.g., "A sequence diagram showing User calling Login API..."). This text is appended to the page content.
    4.  **Chunking**: Accumulates text until `chunk_size` is reached, then splits.
    5.  **Metadata**: Tracks the "Source Page Number" for every chunk, ensuring the Agent can cite its sources (e.g., "Found on Page 5").

### `utils.vector_store.GoogleVectorStore`
A unified interface for Vector Search.

*   **`ingest_chunks(chunks)`**:
    1.  Embeds every chunk using `text-embedding-004`.
    2.  Adds the embedding + metadata to the `local_store` (List of dicts).
*   **`search(query, k=3, filter_metadata={})`**:
    1.  Embeds the query string.
    2.  **Filter Step**: Reduces the search space to only those items matching `filter_metadata` (e.g., `{'type': 'style_guide'}`).
    3.  **Similarity Step**: Calculates Cosine Similarity between the query vector and valid candidates.
    4.  Returns the top `k` matches.
*   **`get_all_by_metadata(filter_metadata)`**:
    *   Bypasses vector search entirely.
    *   Returns **every** chunk that matches the filter. Used for retrieving the *entire* Style Guide to ensure 100% compliance.
*   **`save_local(path)` / `load_local(path)`**:
    *   Persists the embeddings to a `.pkl` file to avoid re-incurring embedding costs and latency on subsequent runs.

## Setup & Running

1.  **Environment**:
    ```bash
    source ~/envs/tf/bin/activate
    pip install google-cloud-aiplatform vertexai scikit-learn pypdf
    ```
2.  **Execution**:
    ```bash
    python ace_agent.py
    ```
