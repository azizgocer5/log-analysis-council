import { useState, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import ChatInterface from './ChatInterface';
import './AnalysisView.css';

function AnalysisView({ analysisState, personas, conversationId, chatMessages, onSendMessage, isChatLoading }) {
  const [activeTab, setActiveTab] = useState('stage3'); // stage1 | stage2 | stage3 | web_search
  const [activePersona, setActivePersona] = useState(0);
  const { status, stage1, stage2, stage3, userQuery, error, reportSaved } = analysisState;

  // Auto-switch to latest active/completed tab
  useEffect(() => {
    if (stage3) {
      setActiveTab('stage3');
    } else if (stage2 && stage2.some(s => s.status === 'complete' || s.evaluation)) {
      setActiveTab('stage2');
    } else if (stage1 && stage1.some(s => s.status === 'complete' || s.response)) {
      setActiveTab('stage1');
    } else if (analysisState.webSearch) {
      setActiveTab('web_search');
    }
  }, [stage1, stage2, stage3, analysisState.webSearch]);

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

  // Loading skeleton (only show if stage1 is not yet initialized)
  if ((status === 'parsing' || status === 'analyzing') && (!stage1 || stage1.length === 0)) {
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

  const completedStage1Count = stage1?.filter(s => s.status === 'complete' || s.response)?.length || 0;
  const completedStage2Count = stage2?.filter(s => s.status === 'complete' || s.evaluation)?.length || 0;

  const tabData = [
    {
      id: 'stage1',
      label: 'Uzman Analizleri',
      icon: '🔬',
      available: !!stage1 && stage1.length > 0,
      count: stage1 && stage1.length > 0 ? `${completedStage1Count}/${stage1.length}` : null,
    },
    {
      id: 'web_search',
      label: 'Araştırma & Referanslar',
      icon: '📚',
      available: !!analysisState.webSearch,
      count: null,
    },
    {
      id: 'stage2',
      label: 'Çapraz Değerlendirme',
      icon: '⚖️',
      available: !!stage2 && stage2.length > 0,
      count: stage2 && stage2.length > 0 ? `${completedStage2Count}/${stage2.length}` : null,
    },
    {
      id: 'stage3',
      label: 'Nihai Rapor',
      icon: '👨‍✈️',
      available: !!stage3,
      count: null,
    },
    {
      id: 'chat',
      label: 'Konsey ile Sohbet',
      icon: '💬',
      available: !!stage3,
      count: null,
    },
  ];

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
            {!tab.available && status !== 'complete' && tab.id !== 'web_search' && (
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

        {activeTab === 'web_search' && analysisState.webSearch && (
          <WebSearchContent webSearch={analysisState.webSearch} />
        )}

        {activeTab === 'stage2' && stage2 && stage2.length > 0 && (
          <Stage2Content
            results={stage2}
            activePersona={activePersona}
            onSelectPersona={setActivePersona}
          />
        )}

        {activeTab === 'stage3' && stage3 && (
          <Stage3Content result={stage3} reportSaved={reportSaved} />
        )}

        {activeTab === 'chat' && (
          <div className="chat-tab-container animate-fade-in" style={{ height: 'calc(100vh - 120px)' }}>
            <ChatInterface
              conversation={conversationId ? { id: conversationId, messages: chatMessages } : null}
              onSendMessage={onSendMessage}
              isLoading={isChatLoading}
            />
          </div>
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
        {results.map((r, i) => {
          const isAnalyzing = r.status === 'analyzing';
          const isComplete = r.status === 'complete' || !!r.response;
          const isPending = !isAnalyzing && !isComplete;
          
          return (
            <button
              key={r.persona_id}
              className={`persona-tab ${i === clampedIndex ? 'active' : ''} ${isPending ? 'pending' : ''}`}
              onClick={() => onSelectPersona(i)}
            >
              <span className="pt-icon">
                {isAnalyzing ? (
                  <span className="persona-spinner">⏳</span>
                ) : (
                  r.persona_icon
                )}
              </span>
              <div className="pt-info">
                <span className="pt-name">
                  {r.persona_name}
                  {isAnalyzing && <span className="pulse-dot"></span>}
                </span>
                <span className="pt-title">
                  {isAnalyzing ? 'Analiz yapıyor...' : isPending ? 'Sırada' : r.persona_title}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      {/* Content */}
      <div className="persona-content animate-fade-in" key={clampedIndex}>
        {current && (current.status === 'complete' || current.response) ? (
          <>
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
          </>
        ) : (
          <div className="persona-skeleton">
            <div className="skeleton-icon animate-pulse">
              {current?.status === 'analyzing' ? '🧠' : '⏳'}
            </div>
            <h3>
              {current?.status === 'analyzing'
                ? `${current.persona_name} Analiz Hazırlıyor...`
                : `${current?.persona_name} Sırasını Bekliyor`}
            </h3>
            <p>
              {current?.status === 'analyzing'
                ? `${current.persona_title} uzmanı uçuş verilerini ve varsa odağı değerlendiriyor.`
                : 'Diğer uzmanların analizleri bittikten sonra bu analiz başlayacaktır.'}
            </p>
            {current?.status === 'analyzing' && (
              <div className="skeleton-lines">
                <div className="skeleton-line"></div>
                <div className="skeleton-line"></div>
                <div className="skeleton-line"></div>
              </div>
            )}
          </div>
        )}
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
        {results.map((r, i) => {
          const isAnalyzing = r.status === 'analyzing';
          const isComplete = r.status === 'complete' || !!r.evaluation;
          const isPending = !isAnalyzing && !isComplete;
          
          return (
            <button
              key={r.persona_id}
              className={`persona-tab ${i === clampedIndex ? 'active' : ''} ${isPending ? 'pending' : ''}`}
              onClick={() => onSelectPersona(i)}
            >
              <span className="pt-icon">
                {isAnalyzing ? (
                  <span className="persona-spinner">⏳</span>
                ) : (
                  r.persona_icon
                )}
              </span>
              <div className="pt-info">
                <span className="pt-name">
                  {r.persona_name}
                  {isAnalyzing && <span className="pulse-dot"></span>}
                </span>
                <span className="pt-title">
                  {isAnalyzing ? 'Değerlendiriyor...' : isPending ? 'Sırada' : 'Değerlendirmesi'}
                </span>
              </div>
            </button>
          );
        })}
      </div>

      <div className="persona-content animate-fade-in" key={clampedIndex}>
        {current && (current.status === 'complete' || current.evaluation) ? (
          <>
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
          </>
        ) : (
          <div className="persona-skeleton">
            <div className="skeleton-icon animate-pulse">
              {current?.status === 'analyzing' ? '⚖️' : '⏳'}
            </div>
            <h3>
              {current?.status === 'analyzing'
                ? `${current.persona_name} Çapraz Değerlendirme Yapıyor...`
                : `${current?.persona_name} Sırasını Bekliyor`}
            </h3>
            <p>
              {current?.status === 'analyzing'
                ? 'Diğer uzmanların analizlerini okuyor ve kendi uzmanlık alanından yorumlar hazırlıyor.'
                : 'Diğer uzmanlar değerlendirme yaptıktan sonra bu değerlendirme başlayacaktır.'}
            </p>
            {current?.status === 'analyzing' && (
              <div className="skeleton-lines">
                <div className="skeleton-line"></div>
                <div className="skeleton-line"></div>
                <div className="skeleton-line"></div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}


function Stage3Content({ result, reportSaved }) {
  const handleDownload = () => {
    if (!reportSaved || !reportSaved.content) return;
    const blob = new Blob([reportSaved.content], { type: 'text/markdown;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', reportSaved.filename || 'council_report.md');
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

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

        {reportSaved && (
          <div className="report-actions">
            <span className="report-save-path" title={`Sunucu kayıt yolu: ${reportSaved.path}`}>
              💾 {reportSaved.filename}
            </span>
            <button className="download-btn" onClick={handleDownload} title="Raporu Markdown (.md) olarak bilgisayarına indir">
              📥 İndir (.md)
            </button>
          </div>
        )}
      </div>
      <div className="chairman-body markdown-content">
        <ReactMarkdown>{result.response}</ReactMarkdown>
      </div>
    </div>
  );
}


function WebSearchContent({ webSearch }) {
  const { answer_vehicles, answer_academic, sources, queries } = webSearch;

  return (
    <div className="web-search-tab-content animate-slide-up">
      <div className="web-search-header">
        <div className="wsh-badge">
          <span className="wsh-icon">🌐</span>
          <div>
            <h3>Gemini Web Araştırması ve Literatür Referansları</h3>
            <p>Google Search Grounding ile gerçek zamanlı taranan veriler ve teknik kaynaklar</p>
          </div>
        </div>
      </div>

      <div className="web-search-body">
        {queries && queries.length > 0 && (
          <div className="web-queries-section">
            <h4>🔍 Yapılan Arama Sorguları:</h4>
            <div className="web-queries-list">
              {queries.map((q, idx) => (
                <span key={idx} className="web-query-tag">{q}</span>
              ))}
            </div>
          </div>
        )}

        <div className="web-answers-container">
          <div className="web-answer-card">
            <h3>🛩️ Benzer Gövdeler ve PID Konfigürasyonları</h3>
            <div className="markdown-content">
              <ReactMarkdown>{answer_vehicles || 'Veri bulunamadı.'}</ReactMarkdown>
            </div>
          </div>

          <div className="web-answer-card">
            <h3>📖 Akademik Referanslar ve Kontrol Teorisi Bulguları</h3>
            <div className="markdown-content">
              <ReactMarkdown>{answer_academic || 'Veri bulunamadı.'}</ReactMarkdown>
            </div>
          </div>
        </div>

        {sources && sources.length > 0 && (
          <div className="web-sources-section animate-slide-up">
            <h3>🔗 Taranan Web Kaynakları ve Makaleler</h3>
            <div className="web-sources-list">
              {sources.map((src, idx) => (
                <a
                  key={idx}
                  href={src.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="web-source-item"
                >
                  <span className="wsi-icon">📄</span>
                  <div className="wsi-info">
                    <span className="wsi-title">{src.title || src.url}</span>
                    <span className="wsi-url">{src.url}</span>
                  </div>
                </a>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AnalysisView;
