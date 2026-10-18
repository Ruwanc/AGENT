import argparse

import chromadb
import ollama

EMBEDDING_MODEL = 'hf.co/CompendiumLabs/bge-base-en-v1.5-gguf'
LANGUAGE_MODEL = 'hf.co/bartowski/Llama-3.2-1B-Instruct-GGUF'
DATA_FILE = "cat.txt"
DB_PATH = "./chroma_db"
COLLECTION_NAME = "cat_data_collection"
BATCH = 32

client = chromadb.PersistentClient(path=DB_PATH)
collection = client.get_or_create_collection(
    name=COLLECTION_NAME,
    metadata={"hnsw:space": "cosine"},
)


def index_file(path=DATA_FILE):
    """Read the file, embed each non-empty line, and upsert into Chroma."""
    with open(path, "r", encoding="utf-8") as f:
        dataset = [line.strip() for line in f if line.strip()]
    print("Total lines:", len(dataset))

    for start in range(0, len(dataset), BATCH):
        batch = dataset[start:start + BATCH]
        embeddings = ollama.embed(model=EMBEDDING_MODEL, input=batch)['embeddings']
        collection.upsert(
            ids=[str(start + i) for i in range(len(batch))],
            documents=batch,
            embeddings=embeddings,
            metadatas=[{"source": path, "line": start + i} for i in range(len(batch))],
        )
        print(f"Added {start + len(batch)}/{len(dataset)}")


def view_collection(n=5):
    """Print the record count and the first n records."""
    print("Records in collection:", collection.count())
    res = collection.get(limit=n, include=["documents", "metadatas"])
    for id_, doc, meta in zip(res["ids"], res["documents"], res["metadatas"]):
        print(f"[{id_}] {meta} {doc[:100]}")


def retrieve(query, top_n=3):
    """Return the top_n (chunk, cosine_similarity) pairs for the query."""
    q = ollama.embed(model=EMBEDDING_MODEL, input=query)['embeddings'][0]
    res = collection.query(
        query_embeddings=[q],
        n_results=top_n,
        include=["documents", "distances"],
    )
    # cosine distance -> similarity
    return [(doc, 1 - dist) for doc, dist in zip(res["documents"][0], res["distances"][0])]


def answer(query, top_n=3):
    """Retrieve context, build a prompt, and stream the model's answer."""
    chunks = retrieve(query, top_n)
    print("\nRetrieved knowledge:")
    for chunk, sim in chunks:
        print(f"  (similarity: {sim:.2f}) {chunk}")

    context = "\n".join(f" - {chunk}" for chunk, _ in chunks)
    system_prompt = (
        "You are a helpful chatbot. Use only the following pieces of context "
        "to answer the question. If the answer is not in the context, say you "
        "don't know. Don't make up new information.\n"
        f"Context:\n{context}"
    )

    print("\nChatbot response:")
    stream = ollama.chat(
        model=LANGUAGE_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": query},
        ],
        stream=True,
    )
    for part in stream:
        print(part["message"]["content"], end="", flush=True)
    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simple RAG over cat.txt with Ollama + ChromaDB")
    parser.add_argument("--reindex", action="store_true", help="(re)build the index from cat.txt")
    parser.add_argument("--view", action="store_true", help="print the first records and exit")
    args = parser.parse_args()

    # Index automatically the first time, or when asked
    if args.reindex or collection.count() == 0:
        index_file()

    if args.view:
        view_collection()
    else:
        while True:
            q = input("\nAsk me a question (blank to quit): ").strip()
            if not q:
                break
            answer(q)
