/**
 * RAG Chatbot frontend.
 *
 * sendMessage() posts to the single stub chat endpoint
 * (POST /api/v1/chatbot/messages/), which currently returns a canned
 * reply from apps/chatbot/services.py::get_bot_reply(). Swapping in a
 * real RAG/LLM backend only requires changing that function — this file
 * and the request/response contract stay the same.
 */
(function () {
  const CHAT_ENDPOINT = '/api/v1/chatbot/messages/';

  const form = document.getElementById('chatForm');
  const input = document.getElementById('chatInput');
  const messages = document.getElementById('chatMessages');
  const csrfToken = document.getElementById('csrfTokenInput').value;

  function scrollToBottom() {
    messages.scrollTop = messages.scrollHeight;
  }

  function appendMessage(text, sender) {
    const wrapper = document.createElement('div');
    wrapper.className = `chat-message chat-message-${sender}`;
    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble';
    bubble.textContent = text;
    wrapper.appendChild(bubble);
    messages.appendChild(wrapper);
    scrollToBottom();
  }

  function showTypingIndicator() {
    const wrapper = document.createElement('div');
    wrapper.className = 'chat-message chat-message-bot';
    wrapper.id = 'chatTypingIndicator';
    wrapper.innerHTML = '<div class="chat-bubble chat-typing-bubble"><span></span><span></span><span></span></div>';
    messages.appendChild(wrapper);
    scrollToBottom();
  }

  function hideTypingIndicator() {
    const indicator = document.getElementById('chatTypingIndicator');
    if (indicator) indicator.remove();
  }

  async function sendMessage(message) {
    // STUB: single integration point for the real RAG/LLM backend — see
    // apps/chatbot/api.py::ChatMessageView and
    // apps/chatbot/services.py::get_bot_reply().
    const response = await fetch(CHAT_ENDPOINT, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({ message }),
    });
    if (!response.ok) {
      throw new Error(`Chat request failed with status ${response.status}`);
    }
    const data = await response.json();
    return data.reply;
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const message = input.value.trim();
    if (!message) return;

    appendMessage(message, 'user');
    input.value = '';
    input.focus();

    showTypingIndicator();
    try {
      const reply = await sendMessage(message);
      hideTypingIndicator();
      appendMessage(reply, 'bot');
    } catch (error) {
      hideTypingIndicator();
      appendMessage('Sorry, something went wrong. Please try again.', 'bot');
      console.error(error);
    }
  });
})();
