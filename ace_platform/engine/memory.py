from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
import pickle
import os

class GenericVectorStore:
    def __init__(self):
        self.store = []

    def add(self, text, metadata=None, embedding=None):
        if embedding is None:
            # In a real engine, we'd call an embedding service here.
            # For header-only implementation, we assume embedding is passed or skipped for now.
            embedding = np.zeros(768) 
        
        self.store.append({
            "text": text,
            "metadata": metadata or {},
            "embedding": embedding
        })

    def search(self, query_vec, k=3, filter_metadata=None):
        # Implementation of the Brute Force search from ace/utils/vector_store.py
        candidates = [item for item in self.store if self._matches(item, filter_metadata)]
        if not candidates: return []
        
        vectors = np.array([c["embedding"] for c in candidates])
        sims = cosine_similarity([query_vec], vectors)[0]
        top_k = sims.argsort()[-k:][::-1]
        
        return [candidates[i] for i in top_k]

    def _matches(self, item, filters):
        if not filters: return True
        return all(item["metadata"].get(k) == v for k, v in filters.items())

class Curator:
    def __init__(self, llm_client, vector_store):
        self.llm = llm_client
        self.memory = vector_store

    def process_critique(self, current_playbook, critique_text):
        # The Abstract Curator Logic
        prompt = f"""
        You are the Curator.
        Critique:
        {critique_text}
        
        Extract imperative rules to prevent these errors. Format as "- Rule".
        """
        response = self.llm.generate(prompt)
        # In a real impl, we would dedup here using self.memory
        return current_playbook + "\n" + response
