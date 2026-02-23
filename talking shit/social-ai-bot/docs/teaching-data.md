# Teaching the bot (knowledge base)

The bot uses **RAG** (retrieval-augmented generation): you add documents and optional Q&A; at runtime the bot retrieves relevant chunks and the LLM answers using that context.

## Adding teaching data

### 1. Directory (default: `data/knowledge`)

Put plain text, Markdown, or PDF files in `data/knowledge/` (or any folder), then run:

```bash
python run_cli.py teach data/knowledge
```

- **Supported formats**: `.txt`, `.md`, `.pdf`
- Subfolders are included. Each file is split into chunks and embedded; the bot will retrieve the most relevant chunks when answering.

### 2. Single file

```bash
python run_cli.py teach --file path/to/notes.md
python run_cli.py teach --file path/to/faq.pdf
```

### 3. What to put in

- **Your own notes**: product info, FAQs, how you want the bot to respond.
- **Exports from other AI**: e.g. ChatGPT conversation exports or markdown summaries. Save as `.md` or `.txt` and run `teach` on that file or folder.

### 4. RAG settings (config.yaml)

Under `rag`:

- `persist_directory`: where Chroma stores vectors (default `./data/chroma`).
- `collection_name`: collection name (default `bot_knowledge`).
- `embedding_model`: OpenAI embedding model (e.g. `text-embedding-3-small`).
- `top_k`: number of chunks retrieved per query (default 4).

Re-running `teach` on the same directory **adds** to the store (it does not replace). To start fresh, delete the `persist_directory` folder and run `teach` again.

## System prompt and persona

Persona and rules are in `src/bot/prompt.py` (`SYSTEM_PROMPT`). Edit that to change tone, boundaries, and how the bot should phrase posts/comments. You can also add few-shot examples in the prompt for consistent style.
