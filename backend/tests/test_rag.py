from app.rag.chunking import chunk_text
from app.services.google_oauth.crypto import token_cipher

def test_token_encryption_at_rest():
    secret_oauth_token = "ya29.a0AfH6SMByTestGoogleToken1234567890"
    encrypted = token_cipher.encrypt(secret_oauth_token)
    assert encrypted != secret_oauth_token
    assert len(encrypted) > 20

    decrypted = token_cipher.decrypt(encrypted)
    assert decrypted == secret_oauth_token

def test_chunking_boundaries():
    sample_text = (
        "Paragraph 1 discusses academic neural networks and transformer self-attention mechanisms.\n\n"
        "Paragraph 2 discusses recurrent connections and memory cells in LSTM architectures.\n\n"
        "Paragraph 3 discusses optimization using AdamW and cosine learning rate schedules."
    )
    chunks = chunk_text(sample_text, chunk_size=200, overlap=50)
    assert len(chunks) >= 2
    assert "Paragraph 1" in chunks[0]["content"]
