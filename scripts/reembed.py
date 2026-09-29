"""Recompute standards.embedding for all rows from combined text.

Constructs text: f"{title}. {scope_text} Keywords: {', '.join(keywords or [])}"
using the same fastembed TextEmbedding model and .embed() call that
app/services/embedding.py uses. Updates ONLY the standards.embedding column.
"""

import sys
import os
import math
import numpy as np

# Add project root to sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import psycopg2
from pgvector.psycopg2 import register_vector
from app import config
from app.services.embedding import build_embedding_text, embed_texts


def reembed_all():
    print(f"Connecting to database {config.DB_NAME} on {config.DB_HOST}:{config.DB_PORT}...")
    conn = psycopg2.connect(
        host=config.DB_HOST,
        port=config.DB_PORT,
        dbname=config.DB_NAME,
        user=config.DB_USER,
        password=config.DB_PASSWORD,
    )
    register_vector(conn)

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, title, scope_text, keywords
            FROM standards
            ORDER BY id
            """
        )
        rows = cur.fetchall()

    if not rows:
        print("No standards found in database.")
        conn.close()
        return

    ids = [r[0] for r in rows]
    texts = [build_embedding_text(r[1], r[2], r[3]) for r in rows]

    print(f"Generating embeddings for {len(texts)} standards using fastembed...")
    embeddings = embed_texts(texts)

    # Calculate vector norm of the first row
    first_vec = embeddings[0]
    sample_norm = math.sqrt(sum(float(x) ** 2 for x in first_vec))
    print(f"Sample vector norm (ID {ids[0]}): {sample_norm:.6f} (dim={len(first_vec)})")

    # Update only the standards.embedding column
    updated_count = 0
    with conn.cursor() as cur:
        for sid, emb in zip(ids, embeddings):
            cur.execute(
                """
                UPDATE standards
                SET embedding = %s
                WHERE id = %s
                """,
                (np.array(emb, dtype=np.float32), sid),
            )
            updated_count += 1
    conn.commit()
    conn.close()

    print(f"Successfully updated {updated_count} rows in standards.embedding.")


if __name__ == "__main__":
    reembed_all()
