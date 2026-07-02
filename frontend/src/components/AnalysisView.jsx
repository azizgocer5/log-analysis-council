import { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import './AnalysisView.css';

function AnalysisView({ analysisState, personas }) {
  const [activeTab, setActiveTab] = useState('stage3'); // stage1 | stage2 | stage3
  const [activePersona, setActivePersona] = useState(0);
  const { status, stage1, stage2, stage3, userQuery, error } = analysisState;

  // Empty state
  if (status === 'idle') {
    return (
      <div className="analysis-empty">
        <div className="empty-content">
          <div className="empty-icon">🛩️</div>
          <h2>UAV Log Analysis Council</h2>
          <p>
            Soldaki panelden uçuş loglarını seçin ve <strong>Council Analizi Başlat</strong> butonuna tıklayın.
          </p>
          <div className="empty-features">
            <div className="empty-feature">
              <span className="ef-icon">🎓</span>
              <div>
                <strong>5 Uzman Persona</strong>
                <p>PID, Vibrasyon, EKF, Güvenlik, Uçuş Testi</p>
              </div>
            </div>
            <div className="empty-feature">
              <span className="ef-icon">📊</span>
              <div>
                <strong>Çoklu Log Karşılaştırma</strong>
                <p>Before/after PID tuning analizi</p>
              </div>
            </div>
            <div className="empty-feature">
              <span className="ef-icon">💊</span>
              <div>
                <strong>PX4 Parametre Reçeteleri</strong>
                <p>Spesifik parametre değişiklik önerileri</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Loading skeleton
  if ((status === 'parsing' || status === 'analyzing') && !stage1) {
    return (
      <div className="analysis-loading">
        <div className="loading-card">
          <div className="loading-icon animate-pulse">🔬</div>
          <h3>Analiz Başlatıldı</h3>
          <p>
            {status === 'parsing'
              ? 'Uçuş logları işleniyor...'
              : 'Uzmanlar analiz yapıyor...'}
          </p>
          {userQuery && (
            <div className="loading-query">
              <span>Soru:</span> {userQuery}
            </div>
          )}
        </div>
      </div>
    );
  }

  // Error state
  if (status === 'error') {
    return (
      <div className="analysis-loading">
        <div className="loading-card error">
          <div className="loading-icon">❌</div>
          <h3>Hata Oluştu</h3>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const tabData = [
    {
      id: 'stage1',
      label: 'Uzman Analizleri',
      icon: '🔬',
      available: !!stage1,
      count: stage1?.length || 0,
    },
    {
      id: 'stage2',
      label: 'Çapraz Değerlendirme',
      icon: '⚖️',
      available: !!stage2 && stage2.length > 0,
      count: stage2?.length || 0,
    },
    {
      id: 'stage3',
      label: 'Nihai Rapor',
      icon: '👨‍✈️',
      available: !!stage3,
      count: null,
    },
  ];

  // Auto-switch to latest completed tab
  const currentData = activeTab === 'stage1' ? stage1
    : activeTab === 'stage2' ? stage2
    : stage3;

  return (
    <div className="analysis-view">
      {/* User query banner */}
      {userQuery && (
        <div className="query-banner">
          <span className="query-label">💬 Soru:</span>
          <span className="query-text">{userQuery}</span>
        </div>
      )}

      {/* Tab bar */}
      <div className="tab-bar">
        {tabData.map((tab) => (
          <button
            key={tab.id}
            className={`tab-btn ${activeTab === tab.id ? 'active' : ''} ${!tab.available ? 'disabled' : ''}`}
            onClick={() => tab.available && setActiveTab(tab.id)}
            disabled={!tab.available}
          >
            <span className="tab-icon">{tab.icon}</span>
            <span className="tab-label">{tab.label}</span>
            {tab.count !== null && tab.available && (
              <span className="tab-count">{tab.count}</span>
            )}
            {!tab.available && status !== 'complete' && (
              <div className="tab-loading">
                <span></span><span></span><span></span>
              </div>
            )}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div className="tab-content">
        {activeTab === 'stage1' && stage1 && (
          <Stage1Content
            results={stage1}
            activePersona={activePersona}
            onSelectPersona={setActivePersona}
          />
        )}

        {activeTab === 'stage2' && stage2 && stage2.length > 0 && (
          <Stage2Content
            results={stage2}
            activePersona={activePersona}
            onSelectPersona={setActivePersona}
          />
        )}

        {activeTab === 'stage3' && stage3 && (
          <Stage3Content result={stage3} />
        )}
      </div>
    </div>
  );
}


function Stage1Content({
  results,
  activePersona,
  onSelectPersona,
}) {
  const clampedIndex = Math.min(activePersona, results.length - 1);
  const current = results[clampedIndex];

  return (
    <div className="stage-content">
      {/* Persona tabs */}
      <div className="persona-tabs">
        {results.map((r, i) => (
          <button
            key={r.persona_id}
            className={`persona-tab ${i === clampedIndex ? 'active' : ''}`}
            onClick={() => onSelectPersona(i)}
          >
            <span className="pt-icon">{r.persona_icon}</span>
            <div className="pt-info">
              <span className="pt-name">{r.persona_name}</span>
              <span className="pt-title">{r.persona_title}</span>
            </div>
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="persona-content animate-fade-in" key={clampedIndex}>
        <div className="persona-header">
          <span className="ph-icon">{current.persona_icon}</span>
          <div>
            <h3>{current.persona_name}</h3>
            <p>{current.persona_title}</p>
          </div>
        </div>
        <div className="markdown-content">
          <ReactMarkdown>{current.response}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}


function Stage2Content({
  results,
  activePersona,
  onSelectPersona,
}) {
  const clampedIndex = Math.min(activePersona, results.length - 1);
  const current = results[clampedIndex];

  return (
    <div className="stage-content">
      <div className="persona-tabs">
        {results.map((r, i) => (
          <button
            key={r.persona_id}
            className={`persona-tab ${i === clampedIndex ? 'active' : ''}`}
            onClick={() => onSelectPersona(i)}
          >
            <span className="pt-icon">{r.persona_icon}</span>
            <div className="pt-info">
              <span className="pt-name">{r.persona_name}</span>
              <span className="pt-title">Değerlendirmesi</span>
            </div>
          </button>
        ))}
      </div>

      <div className="persona-content animate-fade-in" key={clampedIndex}>
        <div className="persona-header">
          <span className="ph-icon">{current.persona_icon}</span>
          <div>
            <h3>{current.persona_name} — Çapraz Değerlendirme</h3>
            <p>{current.persona_title}</p>
          </div>
        </div>
        <div className="markdown-content">
          <ReactMarkdown>{current.evaluation}</ReactMarkdown>
        </div>
      </div>
    </div>
  );
}


function Stage3Content({ result }) {
  return (
    <div className="stage3-content animate-slide-up">
      <div className="chairman-header">
        <div className="chairman-badge">
          <span className="cb-icon">{result.persona_icon || '👨‍✈️'}</span>
          <div>
            <h3>{result.persona_name || 'Baş Mühendis'}</h3>
            <p>{result.persona_title || 'Council Nihai Raporu'}</p>
          </div>
        </div>
      </div>
      <div className="chairman-body markdown-content">
        <ReactMarkdown>{result.response}</ReactMarkdown>
      </div>
    </div>
  );
}


export default AnalysisView;
