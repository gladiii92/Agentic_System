"""
Debug-Skript 6 -- SYNTHETISCHER Test von embedding_filter.py, komplett
unabhaengig von echten Vault-Dateien/Snapshots (Chat-Verlauf 2026-08-24).
Testet NUR die Kernfrage: liefert die Cosinus-Aehnlichkeits-Berechnung
fuer zwei NACHWEISLICH unterschiedliche Texte tatsaechlich einen Wert
DEUTLICH unter 1.000?
"""
from sentence_transformers import SentenceTransformer
import numpy as np

model = SentenceTransformer("all-MiniLM-L6-v2")

text_a = """
| 8 — FIS-Integration | Offen |
Alle Phasen sind in Arbeit.
"""

text_b = """
| 8 — FIS-Integration | Offen | Phase 8 wurde am 2026-08-24 abgeschlossen |
Alle Phasen sind abgeschlossen UND das Projekt ist FERTIG!(22.08.2026)
"""

emb_a = model.encode([text_a])[0]
emb_b = model.encode([text_b])[0]

def cosine(a, b):
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

similarity = cosine(emb_a, emb_b)
print(f"Aehnlichkeit zwischen klar unterschiedlichen Texten: {similarity:.6f}")

# Zusatz-Test: identischer Text mit sich selbst -- MUSS exakt 1.0 sein
emb_a2 = model.encode([text_a])[0]
similarity_self = cosine(emb_a, emb_a2)
print(f"Aehnlichkeit Text A mit sich selbst (Kontrolle): {similarity_self:.6f}")
