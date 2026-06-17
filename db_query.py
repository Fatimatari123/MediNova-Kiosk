"""
db_query.py — MediNova database query engine.
Queries the SQLite database built from the Kaggle disease-symptom dataset
(773 diseases, 377 symptoms, 246,945 records).

Usage:
    from db_query import MediNovaDB
    db = MediNovaDB()
    results = db.find_diseases(["chest pain", "shortness of breath", "fever"])
"""

import sqlite3
import os
import re

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "medinova.db")

# Map common Urdu symptom words → English symptom names in the database
URDU_TO_ENGLISH = {
    # Pain
    "درد": ["pain", "sharp pain", "chest pain", "abdominal pain"],
    "سینہ": ["chest pain", "chest tightness", "sharp chest pain"],
    "سینے": ["chest pain", "chest tightness", "sharp chest pain"],
    "سر": ["headache", "head pain"],
    "سردرد": ["headache"],
    "پیٹ": ["abdominal pain", "stomach pain", "nausea"],
    "آنکھ": ["eye pain", "eye redness", "blurred vision"],
    "آنکھیں": ["eye pain", "eye redness", "blurred vision"],
    "کمر": ["back pain", "lower back pain"],
    "گلا": ["sore throat", "throat pain"],
    "کان": ["ear pain", "ear discharge"],
    "ناک": ["runny nose", "nasal congestion"],
    "جوڑ": ["joint pain", "joint swelling"],
    "گھٹنا": ["knee pain", "joint pain"],
    "کندھا": ["shoulder pain"],
    # Symptoms
    "بخار": ["fever", "high fever", "chills"],
    "کھانسی": ["cough", "coughing"],
    "سانس": ["shortness of breath", "breathing fast", "difficulty breathing"],
    "متلی": ["nausea", "vomiting"],
    "قے": ["vomiting", "nausea"],
    "تھکاوٹ": ["fatigue", "weakness", "tiredness"],
    "کمزوری": ["weakness", "fatigue"],
    "چکر": ["dizziness", "lightheadedness"],
    "دانے": ["skin rash", "rash", "itching"],
    "خارش": ["itching", "skin rash"],
    "پسینہ": ["sweating", "excessive sweating"],
    "دل": ["palpitations", "irregular heartbeat"],
    "نیند": ["insomnia", "sleep disturbances"],
    "بھوک": ["loss of appetite", "decreased appetite"],
    "پانی": ["dehydration", "excessive thirst"],
    "پیشاب": ["frequent urination", "painful urination"],
    "دست": ["diarrhea", "loose stools"],
    "قبض": ["constipation"],
    "سوجن": ["swelling", "edema"],
    # English keywords users might say
    "pain": ["pain", "sharp pain"],
    "fever": ["fever", "high fever", "chills"],
    "cough": ["cough", "coughing"],
    "headache": ["headache"],
    "chest": ["chest pain", "chest tightness", "sharp chest pain"],
    "stomach": ["abdominal pain", "stomach pain", "nausea"],
    "back": ["back pain", "lower back pain"],
    "eye": ["eye pain", "eye redness", "blurred vision"],
    "throat": ["sore throat", "throat pain"],
    "nausea": ["nausea", "vomiting"],
    "fatigue": ["fatigue", "weakness"],
    "dizziness": ["dizziness", "lightheadedness"],
    "rash": ["skin rash", "rash", "itching"],
    "vomiting": ["vomiting", "nausea"],
    "breathing": ["shortness of breath", "breathing fast"],
    "weakness": ["weakness", "fatigue"],
    "swelling": ["swelling", "edema"],
    "diarrhea": ["diarrhea"],
    "cold": ["runny nose", "nasal congestion", "cough"],
    "flu": ["fever", "cough", "fatigue", "headache"],
    "dengue": ["fever", "joint pain", "skin rash", "headache"],
    "malaria": ["fever", "chills", "sweating", "headache"],
}


class MediNovaDB:
    def __init__(self, db_path=DB_PATH):
        self.db_path = db_path
        self._conn = None

    def _get_conn(self):
        if not self._conn:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
        return self._conn

    def extract_symptoms(self, user_text: str) -> list[str]:
        """
        Convert free-form Urdu/English patient text into database symptom keywords.
        Returns a list of English symptom strings that exist in the database.
        """
        text = user_text.lower()
        matched = set()

        for urdu_word, english_symptoms in URDU_TO_ENGLISH.items():
            if urdu_word in text:
                matched.update(english_symptoms)

        # Also check if any exact English symptom names appear directly
        conn = self._get_conn()
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT symptom FROM disease_symptoms")
        all_symptoms = [row[0] for row in cur.fetchall()]

        for sym in all_symptoms:
            if sym.lower() in text:
                matched.add(sym)

        return list(matched)

    def find_diseases(self, symptoms: list[str], top_n: int = 5) -> list[dict]:
        """
        Given a list of symptom strings, find the top_n most likely diseases
        by counting how many of the patient's symptoms match each disease.

        Returns list of dicts with keys: name, matched_symptoms, total_symptoms, score
        """
        if not symptoms:
            return []

        conn = self._get_conn()
        cur  = conn.cursor()

        # For each symptom, find which diseases have it, then score by overlap
        placeholders = ",".join("?" * len(symptoms))
        cur.execute(f"""
            SELECT
                d.name,
                d.symptom_list,
                d.symptom_count,
                COUNT(ds.symptom) AS matched_count
            FROM disease_symptoms ds
            JOIN diseases d ON d.id = ds.disease_id
            WHERE ds.symptom IN ({placeholders})
            GROUP BY d.id
            ORDER BY matched_count DESC, d.symptom_count ASC
            LIMIT ?
        """, symptoms + [top_n])

        rows = cur.fetchall()
        results = []
        for row in rows:
            matched = [s for s in symptoms if s in row["symptom_list"]]
            score = row["matched_count"] / max(len(symptoms), 1)
            results.append({
                "name": row["name"],
                "matched_symptoms": matched,
                "total_symptoms": row["symptom_count"],
                "matched_count": row["matched_count"],
                "score": round(score, 2)
            })

        return results

    def get_disease_info(self, disease_name: str) -> dict | None:
        """Get full symptom profile for a specific disease."""
        conn = self._get_conn()
        cur  = conn.cursor()
        cur.execute(
            "SELECT name, symptom_list, symptom_count FROM diseases WHERE name = ?",
            (disease_name.lower(),)
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "name": row["name"],
            "symptoms": row["symptom_list"].split("|"),
            "symptom_count": row["symptom_count"]
        }

    def stats(self) -> dict:
        """Return database statistics for display."""
        conn = self._get_conn()
        cur  = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM diseases")
        d = cur.fetchone()[0]
        cur.execute("SELECT COUNT(DISTINCT symptom) FROM disease_symptoms")
        s = cur.fetchone()[0]
        return {"diseases": d, "symptoms": s}

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
