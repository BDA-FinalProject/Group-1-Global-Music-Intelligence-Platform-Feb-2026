"""
Chat response service.

get_bot_reply() is the single integration point for a real RAG/LLM
backend. It currently returns a canned placeholder reply regardless of
input, so the chat UI is fully interactive in demo mode. Replace its body
with a real call to the retrieval-augmented pipeline (retrieve context
from the Gold layer, then generate a grounded answer) when the backend is
ready — apps/chatbot/api.py and the frontend don't need to change.
"""
import random

_CANNED_REPLIES = [
    "That's a great question! Once the RAG pipeline is connected, I'll answer using real data from the Gold layer.",
    "I'm running in demo mode right now — my answers will be grounded in real pipeline data once the LLM backend is wired in.",
    "Thanks for trying the chatbot! This response is a placeholder until retrieval-augmented generation is connected.",
]


def get_bot_reply(user_message):
    """STUB: returns a canned demo reply. Swap this for a real RAG/LLM call."""
    return random.choice(_CANNED_REPLIES)
