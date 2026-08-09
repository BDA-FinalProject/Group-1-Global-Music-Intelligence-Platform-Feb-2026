# RAG Chatbot

This work lives in [`../webapp/apps/chatbot/`](../webapp/apps/chatbot/) — it's part of a
self-contained Django application (dashboard + chatbot + supporting pages) rather than a
standalone module, so it's kept together with the rest of that app instead of split out here.

See [`../webapp/README.md`](../webapp/README.md) for the full write-up: the RAG pipeline
(SQL router, hybrid retrieval, reranking, confidence gate, conversational memory), the Gold-layer
schema it queries, and how it's deployed.
