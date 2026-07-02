import { useState } from 'react';
import './LogPanel.css';

function LogPanel({
  logs, sessions, selectedLogIds,
  onToggleLog, onSelectAll, onAnalyze, onAskQuestion, onStop,
  isAnalyzing, personas, selectedModel, setSelectedModel,
}) {
  const [expandedSessions, setExpandedSessions] = useState({});
  const [questionText, setQuestionText] = useState('');
  const [mode, setMode] = useState('analyze'); // analyze | question

  const toggleSession = (session) => {
    setExpandedSessions((prev) => ({
      ...prev,
      [session]: !prev[session],
    }));
  };

  const handleAnalyzeClick = () => {
    if (mode === 'question' && questionText.trim()) {
      onAskQuestion(questionText.trim());
    } else {
      onAnalyze(questionText.trim() || null);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleAnalyzeClick();
    }
  };

  const selectedCount = selectedLogIds.length;
  const sortedSessions = Object.keys(sessions).sort().reverse();

  return (
    <div className="log-panel">
      {/* Header */}
      <div className="log-panel-header">
        <div className="brand">
          <div className="brand-icon">✈️</div>
          <div>
            <h1>UAV Council</h1>
            <p>Log Analysis System</p>
          </div>
        </div>
      </div>

      {/* Persona badges */}
      {personas && (
        <div className="persona-badges">
          {personas.personas?.map((p) => (
            <div key={p.id} className="persona-badge" style={{ borderColor: 'var(--border-active)' }}>
              <span className="persona-badge-icon">{p.icon}</span>
              <span className="persona-badge-name">{p.name}</span>
            </div>
          ))}
        </div>
      )}

      {/* Selection info */}
      <div className="selection-info">
        <span className="selection-count">{selectedCount}</span>
        <span className="selection-label">log seçili</span>
        {selectedCount > 0 && (
          <button
            className="clear-btn"
            onClick={() => selectedLogIds.forEach(id => onToggleLog(id))}
          >
            Temizle
          </button>
        )}
      </div>

      {/* Log list */}
      <div className="log-list">
        {sortedSessions.map((session) => {
          const sessionLogs = sessions[session] || [];
          const isExpanded = expandedSessions[session] !== false; // Default open
          const selectedInSession = sessionLogs.filter((l) =>
            selectedLogIds.includes(l.id)
          ).length;

          return (
            <div key={session} className="session-group">
              <div
                className="session-header"
                onClick={() => toggleSession(session)}
              >
                <div className="session-left">
                  <span className={`session-chevron ${isExpanded ? 'expanded' : ''}`}>▶</span>
                  <span className="session-name">{session}</span>
                  <span className="session-count">{sessionLogs.length}</span>
                </div>
                {sessionLogs.length > 1 && (
                  <button
                    className="select-all-btn"
                    onClick={(e) => {
                      e.stopPropagation();
                      onSelectAll(sessionLogs);
                    }}
                  >
                    {selectedInSession === sessionLogs.length ? '✓ Hepsi' : 'Tümünü Seç'}
                  </button>
                )}
              </div>

              {isExpanded && (
                <div className="session-logs">
                  {sessionLogs.map((log) => {
                    const isSelected = selectedLogIds.includes(log.id);
                    return (
                      <div
                        key={log.id}
                        className={`log-item ${isSelected ? 'selected' : ''}`}
                        onClick={() => onToggleLog(log.id)}
                      >
                        <div className="log-checkbox">
                          {isSelected ? '☑' : '☐'}
                        </div>
                        <div className="log-info">
                          <span className="log-name">{log.filename}</span>
                          <span className="log-meta">
                            {log.size_mb} MB
                            {log.cached && <span className="cache-badge">cached</span>}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Action area */}
      <div className="action-area">
        {/* Mode toggle */}
        <div className="mode-toggle">
          <button
            className={`mode-btn ${mode === 'analyze' ? 'active' : ''}`}
            onClick={() => setMode('analyze')}
            disabled={isAnalyzing}
          >
            🔬 Tam Analiz
          </button>
          <button
            className={`mode-btn ${mode === 'question' ? 'active' : ''}`}
            onClick={() => setMode('question')}
            disabled={isAnalyzing}
          >
            💬 Soru Sor
          </button>
        </div>

        {/* Model Selector */}
        <div className="model-toggle">
          <button
            className={`mode-btn ${selectedModel === 'qwen3:8b' ? 'active' : ''}`}
            onClick={() => setSelectedModel('qwen3:8b')}
            disabled={isAnalyzing}
          >
            🤖 Ollama (qwen3:8b)
          </button>
          <button
            className={`mode-btn ${selectedModel === 'gemini-flash-latest' ? 'active' : ''}`}
            onClick={() => setSelectedModel('gemini-flash-latest')}
            disabled={isAnalyzing}
          >
            ⚡ Gemini (Flash)
          </button>
        </div>

        {/* Question input */}
        <div className="question-input-wrapper">
          <textarea
            className="question-input"
            placeholder={
              mode === 'question'
                ? 'Loglar hakkında soru sorun...'
                : 'Opsiyonel: Analiz odağı belirtin (örn: "PID tuning üzerine yoğunlaş")...'
            }
            value={questionText}
            onChange={(e) => setQuestionText(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={2}
            disabled={isAnalyzing}
          />
        </div>

        {/* Analyze or Stop button */}
        {isAnalyzing ? (
          <button
            className="stop-btn"
            onClick={onStop}
          >
            🛑 Analizi Durdur
          </button>
        ) : (
          <button
            className="analyze-btn"
            onClick={handleAnalyzeClick}
            disabled={mode === 'analyze' && selectedCount === 0}
          >
            {mode === 'question' ? (
              <>💬 Soru Gönder</>
            ) : (
              <>🚀 Council Analizi Başlat ({selectedCount} log)</>
            )}
          </button>
        )}
      </div>
    </div>
  );
}

export default LogPanel;
