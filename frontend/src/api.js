/**
 * API client for the UAV Log Analysis Council backend.
 */

const API_BASE = 'http://localhost:8001';

/**
 * Generic SSE stream reader.
 * @param {Response} response - Fetch response
 * @param {function} onEvent - Callback: (eventType, data) => void
 */
async function readSSEStream(response, onEvent) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // Keep incomplete line in buffer

    for (const line of lines) {
      if (line.startsWith('data: ')) {
        try {
          const event = JSON.parse(line.slice(6));
          onEvent(event.type, event);
        } catch (e) {
          console.error('Failed to parse SSE event:', e);
        }
      }
    }
  }
}

export const api = {
  // ---- Log Management ----

  /** List all available ULog files */
  async listLogs() {
    const response = await fetch(`${API_BASE}/api/logs`);
    if (!response.ok) throw new Error('Failed to list logs');
    return response.json();
  },

  /** Get summary for a specific log */
  async getLogSummary(logId) {
    const response = await fetch(`${API_BASE}/api/logs/${logId}/summary`);
    if (!response.ok) throw new Error('Failed to get log summary');
    return response.json();
  },

  /** Get council personas */
  async getPersonas() {
    const response = await fetch(`${API_BASE}/api/personas`);
    if (!response.ok) throw new Error('Failed to get personas');
    return response.json();
  },

  /** Get cache stats */
  async getCacheStats() {
    const response = await fetch(`${API_BASE}/api/cache/stats`);
    if (!response.ok) throw new Error('Failed to get cache stats');
    return response.json();
  },

  // ---- Analysis (Streaming) ----

  /**
   * Run full council analysis on selected logs.
   * @param {string[]} logIds - Selected log IDs
   * @param {string|null} userQuery - Optional user question
   * @param {string} model - Selected model name
   * @param {AbortSignal} [signal] - Optional abort signal
   * @param {function} onEvent - SSE callback
   */
  async analyzeStream(logIds, userQuery, model, signal, onEvent) {
    const response = await fetch(`${API_BASE}/api/analyze/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ log_ids: logIds, user_query: userQuery, model: model }),
      signal: signal,
    });
    if (!response.ok) throw new Error('Failed to start analysis');
    await readSSEStream(response, onEvent);
  },

  /**
   * Ask a free-form question to the council.
   * @param {string} question - The question
   * @param {string[]|null} logIds - Optional log context
   * @param {string} model - Selected model name
   * @param {AbortSignal} [signal] - Optional abort signal
   * @param {function} onEvent - SSE callback
   */
  async askQuestionStream(question, logIds, model, signal, onEvent) {
    const response = await fetch(`${API_BASE}/api/ask/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question, log_ids: logIds, model: model }),
      signal: signal,
    });
    if (!response.ok) throw new Error('Failed to ask question');
    await readSSEStream(response, onEvent);
  },

  // ---- Conversations ----

  async listConversations() {
    const response = await fetch(`${API_BASE}/api/conversations`);
    if (!response.ok) throw new Error('Failed to list conversations');
    return response.json();
  },

  async createConversation() {
    const response = await fetch(`${API_BASE}/api/conversations`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    if (!response.ok) throw new Error('Failed to create conversation');
    return response.json();
  },

  async getConversation(conversationId) {
    const response = await fetch(`${API_BASE}/api/conversations/${conversationId}`);
    if (!response.ok) throw new Error('Failed to get conversation');
    return response.json();
  },

  async sendMessageStream(conversationId, content, logIds, model, onEvent) {
    const response = await fetch(
      `${API_BASE}/api/conversations/${conversationId}/message/stream`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content, log_ids: logIds, model: model }),
      }
    );
    if (!response.ok) throw new Error('Failed to send message');
    await readSSEStream(response, onEvent);
  },
};
