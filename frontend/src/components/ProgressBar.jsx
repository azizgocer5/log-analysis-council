import './ProgressBar.css';

function ProgressBar({ analysisState }) {
  const { status, parsingProgress, currentStage } = analysisState;

  if (status === 'idle') return null;

  const stages = [
    { id: 'parsing', label: 'Log Parsing', icon: '📊' },
    { id: 1, label: 'Uzman Analizleri', icon: '🔬' },
    { id: 2, label: 'Çapraz Değerlendirme', icon: '⚖️' },
    { id: 3, label: 'Başkan Sentezi', icon: '👨‍✈️' },
  ];

  const getStageStatus = (stageId) => {
    if (status === 'complete') return 'complete';
    if (status === 'error') return 'error';

    if (stageId === 'parsing') {
      if (status === 'parsing') return 'active';
      return 'complete';
    }

    if (status === 'parsing') return 'pending';

    if (typeof stageId === 'number') {
      if (currentStage > stageId) return 'complete';
      if (currentStage === stageId) return 'active';
      return 'pending';
    }

    return 'pending';
  };

  // Calculate progress percentage
  let progressPercent = 0;
  if (status === 'complete') {
    progressPercent = 100;
  } else if (status === 'parsing' && parsingProgress) {
    progressPercent = (parsingProgress.current / parsingProgress.total) * 20;
  } else if (currentStage) {
    progressPercent = 20 + (currentStage / 3) * 80;
  }

  return (
    <div className="progress-bar-wrapper">
      <div className="progress-stages">
        {stages.map((stage) => {
          const stageStatus = getStageStatus(stage.id);
          return (
            <div key={stage.id} className={`progress-stage ${stageStatus}`}>
              <div className="progress-stage-icon">
                {stageStatus === 'complete' ? '✅' :
                 stageStatus === 'active' ? stage.icon :
                 stageStatus === 'error' ? '❌' :
                 '○'}
              </div>
              <span className="progress-stage-label">{stage.label}</span>
              {stageStatus === 'active' && (
                <div className="progress-dot-loader">
                  <span></span><span></span><span></span>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="progress-bar-track">
        <div
          className="progress-bar-fill-animated"
          style={{ width: `${progressPercent}%` }}
        />
      </div>

      {status === 'parsing' && parsingProgress && (
        <div className="progress-detail">
          {parsingProgress.complete
            ? '✅ Tüm loglar işlendi'
            : `📂 ${parsingProgress.filename || '...'} işleniyor (${parsingProgress.current}/${parsingProgress.total})`
          }
          {parsingProgress.fromCache && ' (cache)'}
        </div>
      )}
    </div>
  );
}

export default ProgressBar;
