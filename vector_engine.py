import os
import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

# Multilingual model that maps 50+ languages (including Urdu) to the same vector space as English
MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'

class MediNovaVectorEngine:
    def __init__(self, csv_path, model_name=MODEL_NAME):
        self.csv_path = csv_path
        self.model = SentenceTransformer(model_name)
        self.index = None
        self.disease_data = []
        self._initialize_engine()

    def _initialize_engine(self):
        """Fetch all diseases from CSV, embed their symptom lists, and build the FAISS index."""
        if not os.path.exists(self.csv_path):
            print(f"Error: CSV file not found at {self.csv_path}")
            return

        print(f"Loading data from {self.csv_path}...")
        df = pd.read_csv(self.csv_path)
        
        # Ensure required columns exist
        required_cols = ['Name', 'Symptoms', 'Treatments']
        for col in required_cols:
            if col not in df.columns:
                print(f"Error: Missing required column '{col}' in CSV.")
                return

        print(f"Indexing {len(df)} diseases for semantic search...")
        
        # Prepare data for embedding
        texts_to_embed = []
        for _, row in df.iterrows():
            name = str(row['Name'])
            symptoms = str(row['Symptoms'])
            treatments = str(row['Treatments'])
            
            # Create a rich description for the vector space
            description = f"Disease: {name}. Symptoms: {symptoms}. Treatments: {treatments}"
            texts_to_embed.append(description)
            
            self.disease_data.append({
                "name": name,
                "symptoms": symptoms,
                "treatments": treatments
            })

        # Generate embeddings
        embeddings = self.model.encode(texts_to_embed, show_progress_bar=True)
        
        # Build FAISS index
        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))
        print("Semantic Index built successfully.")

    def search(self, query_text, top_n=5):
        """
        Query the index using Urdu or English text. 
        Returns top matching diseases with similarity scores.
        """
        if self.index is None:
            return []

        # Encode the query (Urdu or English) into the same vector space
        query_vector = self.model.encode([query_text])
        
        # Search the index
        distances, indices = self.index.search(np.array(query_vector).astype('float32'), top_n)
        
        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1: continue
            
            disease = self.disease_data[idx]
            # Convert L2 distance to a "confidence" score (0 to 1)
            score = 1 / (1 + distances[0][i])
            
            results.append({
                "name": disease["name"],
                "symptoms": disease["symptoms"],
                "treatments": disease["treatments"],
                "confidence": round(float(score), 4)
            })
            
        return results

if __name__ == "__main__":
    # Test script
    csv_file = r"C:\Users\Fatima\medinova_kiosk\data\Diseases_Symptoms.csv"
    engine = MediNovaVectorEngine(csv_file)
    
    # Test with Urdu query
    test_query = "میرے سینے میں شدید درد اور پسینہ آ رہا ہے"
    print(f"\nTesting Query (Urdu): {test_query}")
    matches = engine.search(test_query)
    for m in matches:
        print(f"- {m['name']} (Confidence: {m['confidence']})")
