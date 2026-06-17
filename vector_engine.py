import os
import re
import pandas as pd
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

try:
    from db_query import URDU_TO_ENGLISH
except ImportError:
    URDU_TO_ENGLISH = {}

MODEL_NAME = 'paraphrase-multilingual-MiniLM-L12-v2'
MIN_MATCH_CONFIDENCE = 0.45


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

        required_cols = ['Name', 'Symptoms', 'Treatments']
        for col in required_cols:
            if col not in df.columns:
                print(f"Error: Missing required column '{col}' in CSV.")
                return

        print(f"Indexing {len(df)} diseases for semantic search...")

        texts_to_embed = []
        for _, row in df.iterrows():
            name = str(row['Name'])
            symptoms = str(row['Symptoms'])
            treatments = str(row['Treatments'])
            recommendation = str(row['Recommendations']) if 'Recommendations' in df.columns else treatments

            description = (
                f"Disease: {name}. Symptoms: {symptoms}. "
                f"Treatments: {treatments}. Recommendations: {recommendation}"
            )
            texts_to_embed.append(description)

            self.disease_data.append({
                "name": name,
                "symptoms": symptoms,
                "treatments": treatments,
                "recommendations": recommendation,
                "symptom_list": self._parse_symptom_list(symptoms),
            })

        embeddings = self.model.encode(texts_to_embed, show_progress_bar=True)

        dimension = embeddings.shape[1]
        self.index = faiss.IndexFlatL2(dimension)
        self.index.add(np.array(embeddings).astype('float32'))
        print("Semantic Index built successfully.")

    @staticmethod
    def _parse_symptom_list(symptoms_text):
        return [s.strip().lower() for s in re.split(r'[,;|]', str(symptoms_text)) if s.strip()]

    def _extract_query_symptom_hints(self, query_text):
        """Map Urdu/English patient text to English symptom hints for overlap scoring."""
        text = query_text.lower()
        hints = set()

        for word, english_symptoms in URDU_TO_ENGLISH.items():
            if word.lower() in text:
                hints.update(s.lower() for s in english_symptoms)

        for disease in self.disease_data:
            for symptom in disease["symptom_list"]:
                if symptom in text or any(part in text for part in symptom.split() if len(part) > 3):
                    hints.add(symptom)

        return hints

    def _compute_symptom_overlap(self, query_text, disease):
        query_hints = self._extract_query_symptom_hints(query_text)
        disease_symptoms = disease["symptom_list"]
        if not disease_symptoms:
            return [], 0.0

        matched = []
        for symptom in disease_symptoms:
            if symptom in query_hints:
                matched.append(symptom)
                continue
            for hint in query_hints:
                if hint in symptom or symptom in hint:
                    matched.append(symptom)
                    break

        overlap_ratio = len(set(matched)) / max(len(disease_symptoms), 1)
        return list(dict.fromkeys(matched)), round(overlap_ratio, 4)

    def search(self, query_text, top_n=5):
        """
        Query the index using Urdu or English text.
        Returns top matching diseases with combined semantic + symptom overlap scores.
        """
        if self.index is None or not query_text.strip():
            return []

        query_vector = self.model.encode([query_text])
        distances, indices = self.index.search(np.array(query_vector).astype('float32'), top_n)

        results = []
        for i, idx in enumerate(indices[0]):
            if idx == -1:
                continue

            disease = self.disease_data[idx]
            semantic_score = 1 / (1 + distances[0][i])
            matched_symptoms, overlap_ratio = self._compute_symptom_overlap(query_text, disease)
            combined_score = round((0.65 * semantic_score) + (0.35 * overlap_ratio), 4)

            results.append({
                "name": disease["name"],
                "symptoms": disease["symptoms"],
                "treatments": disease["treatments"],
                "recommendations": disease["recommendations"],
                "matched_symptoms": matched_symptoms,
                "symptom_overlap": overlap_ratio,
                "confidence": combined_score,
            })

        results.sort(key=lambda x: x["confidence"], reverse=True)
        return results

    def get_valid_matches(self, query_text, top_n=5, min_confidence=MIN_MATCH_CONFIDENCE):
        return [m for m in self.search(query_text, top_n=top_n) if m.get("confidence", 0) >= min_confidence]

    def format_for_llm(self, matches):
        """Format dataset matches as structured evidence for the LLM."""
        if not matches:
            return "No relevant medical conditions found in the database."

        blocks = []
        for i, match in enumerate(matches, 1):
            matched_symptoms = match.get("matched_symptoms") or []
            supporting = ", ".join(matched_symptoms) if matched_symptoms else "See dataset symptoms below"
            blocks.append(
                f"Dataset Match {i}:\n"
                f"  Condition: {match['name']}\n"
                f"  Confidence: {match.get('confidence', 0)}\n"
                f"  Supporting/Matched Symptoms: {supporting}\n"
                f"  All Dataset Symptoms: {match['symptoms']}\n"
                f"  Possible Treatment: {match['treatments']}\n"
                f"  Recommendation: {match.get('recommendations', match['treatments'])}"
            )
        return "\n\n".join(blocks)


if __name__ == "__main__":
    csv_file = os.path.join(os.path.dirname(__file__), "data", "Diseases_Symptoms.csv")
    engine = MediNovaVectorEngine(csv_file)

    test_query = "میرے سینے میں شدید درد اور پسینہ آ رہا ہے"
    print(f"\nTesting Query (Urdu): {test_query}")
    matches = engine.search(test_query)
    for m in matches:
        print(f"- {m['name']} (Confidence: {m['confidence']}, Matched: {m['matched_symptoms']})")
