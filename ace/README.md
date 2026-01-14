# ACE Agent Implementation

This folder contains an implementation of the **Agentic Context Engineering (ACE)** framework, adapted to generate an OpenAPI Specification from a Product Spec and Style Guide.

## Prerequisites

1.  **GCP Project**: Ensure you have a Google Cloud Project with Vertex AI enabled.
    *   **Embeddings**: The `text-embedding-004` model is used for deduplication.
    *   **Generation**: The `gemini-1.5-flash-001` model is used for the Agent roles (Generator, Reflector, Curator).
    *   *Note: If you encounter 404/NotFound errors, ensure the "Vertex AI Generative AI API" is enabled and your service account has access.*

2.  **Environment**:
    *   Python 3.10+
    *   `google-cloud-aiplatform`
    *   `scikit-learn` (for cosine similarity)
    *   `numpy`

## Usage

1.  **Prepare Documents**: Place your `product_spec.txt` and `style_guide.txt` in the `docs/` folder. (PDFs can be converted using `pdftotext`).
2.  **Run the Agent**:
    ```bash
    # Activate your env
    source ~/envs/tf/bin/activate
    
    # Run the script
    python ace_agent.py
    ```

## How It Works

1.  **Generator**: Drafts an initial OpenAPI Spec based on the `product_spec` and the current "Context Playbook".
2.  **Reflector**: Critiques the generated spec against the `style_guide.txt`.
3.  **Curator**: Synthesizes the critique into new "lessons learned".
    *   **Deduplication**: It uses `text-embedding-004` to embed new lessons and compares them against the existing playbook using cosine similarity. If a lesson is too similar (>0.85), it is skipped to prevent context bloat.
4.  **Loop**: This cycle repeats for a configurable number of epochs (default: 3) to refine the output.
