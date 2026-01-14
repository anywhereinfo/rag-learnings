
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
        self.cross_encoder = None
        
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

    def search(self, query, k=3, filter_metadata=None, rerank=False):
        """
        Search for relevant chunks with optional metadata filtering and Reranking.
        """
        query_embedding = self.embed_text(query)
        
        # 0. Candidates Selection 
        # (Same logic as before, but if rerank=True, we fetch more candidates)
        initial_k = k * 5 if rerank else k
        
        # ... (Existing Google Index Logic Placeholder) ...

        # 2. Local Partial Search
        raw_candidates = []
        for item in self.local_store:
            if filter_metadata:
                if all(item['metadata'].get(key) == val for key, val in filter_metadata.items()):
                    raw_candidates.append(item)
            else:
                raw_candidates.append(item)
        
        if not raw_candidates: return []

        # Cosine Similarity (The "Retriever")
        q_vec = np.array(query_embedding).reshape(1, -1)
        store_matrix = np.array([item['embedding'] for item in raw_candidates])
        from sklearn.metrics.pairwise import cosine_similarity
        sims = cosine_similarity(q_vec, store_matrix)[0]
        
        top_indices = sims.argsort()[-initial_k:][::-1]
        preliminary_results = [raw_candidates[i] for i in top_indices]

        if not rerank:
            return preliminary_results

        # 3. Reranking (The "Cross Encoder")
        if not self.cross_encoder:
             try:
                 from sentence_transformers import CrossEncoder
                 print("Loading CrossEncoder (ms-marco-MiniLM-L-6-v2)...")
                 self.cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
             except Exception as e:
                 print(f"Failed to load CrossEncoder: {e}. Returning raw results.")
                 return preliminary_results[:k]

        print(f"Reranking {len(preliminary_results)} candidates for: '{query}'")
        pairs = [[query, item['text']] for item in preliminary_results]
        scores = self.cross_encoder.predict(pairs)
        
        # augment results with score
        for i, res in enumerate(preliminary_results):
            res['score'] = scores[i]
            
        # Sort by CrossEncoder score
        reranked = sorted(preliminary_results, key=lambda x: x['score'], reverse=True)
        return reranked[:k]

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
