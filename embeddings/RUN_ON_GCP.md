# Running on Google Cloud Platform (GCP)

While the `test_emb.py` script already uses GCP's Vertex AI for generating embeddings (via API), the local script handles the data processing (PCA) and visualization.

If you want to move the entire execution environment to the cloud (e.g., to avoid local setup, leverage cloud networking, or keep data within GCP), the recommended approach is using **Vertex AI Workbench**.

## Option 1: Vertex AI Workbench (Recommended)

Vertex AI Workbench provides a JupyterLab environment pre-configured with many data science tools.

### 1. Create a Notebook Instance
1.  Go to the [Vertex AI Workbench](https://console.cloud.google.com/vertex-ai/workbench) console.
2.  Create a new **User-Managed Notebook** (or "Instance").
3.  Select **Python 3** (TensorFlow/PyTorch versions are fine, but generic Python 3 is sufficient).
4.  Ensure it is in the same region as your resources (e.g., `us-central1`).
5.  Click **Create**.

### 2. Clone the Repository
1.  Once the JupyterLab interface is open, open a **Terminal**.
2.  Run the git clone command:
    ```bash
    git clone https://github.com/anywhereinfo/rag-learnings.git
    cd rag-learnings/embeddings
    ```

### 3. Install Dependencies
In the terminal (or a notebook cell), install the required libraries:
```bash
pip install -r requirements.txt
```
*(Note: You may need to create a `requirements.txt` first or simply run: `pip install scikit-learn matplotlib google-cloud-aiplatform`)*

### 4. Run the Code

**As a Script:**
You can run the python script directly from the terminal:
```bash
python test_emb.py
```
*Note: `plt.show()` will not pop up a window in the terminal. The script saves images (`pca_embeddings.png`), which you can double-click in the file browser to view.*

**As a Notebook (Interactive):**
For a better experience, create a new `.ipynb` file and copy the code blocks there. This allows you to see the plots inline.

## Authentication
Vertex AI Workbench instances operate with a Service Account. Ensure this service account has the **Vertex AI User** role. You generally do not need to use `gcloud auth login` inside the notebook if the instance permissions are set correctly.
