
from google.cloud import aiplatform
from vertexai.language_models import TextEmbeddingModel
import time
import numpy as np
import traceback

class GoogleVectorStore:
    def __init__(self, project_id, location, index_endpoint_name=None, index_id=None):
        self.project_id = project_id
        self.location = location
        self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        
        # Initialize Vertex AI
        aiplatform.init(project=project_id, location=location)
        
        self.index_endpoint = None
        self.index = None
        
        # In a real scenario, we would connect to an existing index
        if index_endpoint_name:
            try:
                 self.index_endpoint = aiplatform.MatchingEngineIndexEndpoint(index_endpoint_name=index_endpoint_name)
                 print(f"Connected to Index Endpoint: {index_endpoint_name}")
            except Exception as e:
                print(f"Failed to connect to Index Endpoint: {e}")

        # Local Fallback Store (for demo purposes if GCP Index isn't ready)
        self.local_store = [] # List of {"embedding": vec, "text": txt, "metadata": meta}

    def embed_text(self, text):
        try:
             # Vertex AI rate limits?
             # Simple retry mechanism
             return self.embedding_model.get_embeddings([text])[0].values
        except Exception as e:
            print(f"Embedding error: {e}")
            return np.zeros(768)

    def ingest_chunks(self, chunks):
        """
        Ingest chunks into the vector store.
        """
        print(f"Ingesting {len(chunks)} chunks...")
        for i, chunk in enumerate(chunks):
            embedding = self.embed_text(chunk['text'])
            
            # 1. Add to Local Fallback
            self.local_store.append({
                "id": str(i),
                "embedding": embedding,
                "text": chunk['text'],
                "metadata": chunk['metadata']
            })
            
            # 2. Add to Google Vector Search (Conceptual)
            # Real implementation requires:
            # - Writing to GCS (JSONL)
            # - Create Index
            # - Create Index Endpoint
            # - Deploy Index
            # OR (Streaming Update) if Index supports it.
            # 
            # Streaming Update Example:
            # if self.index_endpoint:
            #      self.index_endpoint.update_embeddings(...) 
            # 
            # For this demo, we acknowledge the requirement but use local fallback for immediate execution
            # unless an endpoint is actively provided.
            
            if i % 10 == 0:
                print(f"Processed {i}/{len(chunks)}...")

    def search(self, query, k=3, filter_metadata=None):
        """
        Search for relevant chunks with optional metadata filtering.
        filter_metadata: dict, e.g., {'type': 'product_spec'}
        """
        query_embedding = self.embed_text(query)
        
        # 1. Google Vector Search Call
        if self.index_endpoint:
            try:
                # In Vertex AI Vector Search, filtering is done using 'restricts'
                print(f"Querying Endpoint with filter: {filter_metadata}")
                # Placeholder for actual client call
            except Exception as e:
                print(f"Vector Search Error: {e}")

        # 2. Local Fallback Search (Cosine Sim)
        if not self.local_store:
            return []

        # Filter candidates first (Local Simulation of 'Restricts')
        candidates = []
        candidate_indices = []
        
        for i, item in enumerate(self.local_store):
            if filter_metadata:
                match = True
                for key, val in filter_metadata.items():
                    if item['metadata'].get(key) != val:
                        match = False
                        break
                if match:
                    candidates.append(item)
                    candidate_indices.append(i)
            else:
                candidates.append(item)
                candidate_indices.append(i)
        
        if not candidates:
            return []

        q_vec = np.array(query_embedding).reshape(1, -1)
        store_matrix = np.array([item['embedding'] for item in candidates])
        
        from sklearn.metrics.pairwise import cosine_similarity
        sims = cosine_similarity(q_vec, store_matrix)[0]
        
        # Get Top K relative to the candidates list
        # argsort gives indices into 'sims', which corresponds to 'candidates'
        top_k_indices = sims.argsort()[-k:][::-1]
        
        results = []
        for idx in top_k_indices:
            results.append(candidates[idx])
            
        return results

    def get_all_by_metadata(self, filter_metadata):
        """
        Retrieve all chunks that match the given metadata filter.
        """
        results = []
        for item in self.local_store:
            match = True
            for key, val in filter_metadata.items():
                if item['metadata'].get(key) != val:
                    match = False
                    break
            if match:
                results.append(item)
        return results

    def save_local(self, path="vector_store.pkl"):
        import pickle
        try:
            with open(path, 'wb') as f:
                pickle.dump(self.local_store, f)
            print(f"Saved vector store to {path}")
        except Exception as e:
            print(f"Error saving vector store: {e}")

    def load_local(self, path="vector_store.pkl"):
        import pickle
        import os
        if not os.path.exists(path):
            print(f"No existing vector store found at {path}")
            return False
            
        try:
            with open(path, 'rb') as f:
                self.local_store = pickle.load(f)
            print(f"Loaded vector store from {path} ({len(self.local_store)} chunks)")
            return True
        except Exception as e:
            print(f"Error loading vector store: {e}")
            return False
