# Embeddings Demo

This directory demonstrates the usage of Vertex AI Text Embeddings to analyze semantic similarity and visualize vector representations.

## `test_emb.py`

The `test_emb.py` script serves as a learning demonstration for:
1.  **Generating Embeddings**: content uses `vertexai.language_models.TextEmbeddingModel` (specifically `text-embedding-004`) to convert text into vector embeddings.
2.  **Cosine Similarity**: It calculates cosine similarity between different text inputs to measure how semantically similar they are.
    *   Example 1: Comparing philosophically related sentences about "life" and "42".
    *   Example 2: Comparing sentences with ambiguous words like "plant" (industrial v.s. biological) to see if the embeddings capture context.
3.  **Dimensionality Reduction (PCA)**: It uses Principal Component Analysis (PCA) to reduce the high-dimensional embedding vectors into 2 dimensions for visualization.
4.  **Visualization**:
    *   Generates a scatter plot (`pca_embeddings.png`) of the 2D PCA-reduced embeddings.
    *   Generates a heatmap (`similarity_heatmap.png`) showing the pairwise cosine similarities between sentences.

## Outputs

The script typically generates two image files in this directory:
- `pca_embeddings.png`: A 2D plot of the first set of sentences.
- `similarity_heatmap.png`: A heatmap showing similarity scores for the second set of sentences.
