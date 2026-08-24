"""
Debug-Skript 7 -- prueft die Token-Truncation-Hypothese: schneidet
all-MiniLM-L6-v2 lange Texte ab, sodass eine Aenderung WEITER HINTEN im
Text (wie bei ROADMAP.md, 7813 Zeichen) gar nicht mehr im Embedding
ankommt? (Chat-Verlauf 2026-08-24)
"""
from sentence_transformers import SentenceTransformer

model = SentenceTransformer("all-MiniLM-L6-v2")

print("max_seq_length des Modells:", model.max_seq_length)

sample_text = "Wort " * 1500  # grobe Annaeherung an 7813 Zeichen
tokens = model.tokenizer(sample_text, truncation=False)
print("Anzahl Tokens bei ca. 7500 Zeichen Text:", len(tokens["input_ids"]))
print("Modell-Token-Limit (max_seq_length):", model.max_seq_length)
print("Wird abgeschnitten?", len(tokens["input_ids"]) > model.max_seq_length)
