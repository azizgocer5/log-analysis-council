import { useState, useEffect } from 'react';
import LogPanel from './components/LogPanel';
import AnalysisView from './components/AnalysisView';
import ProgressBar from './components/ProgressBar';
import { api } from './api';
import './App.css';

function App() {
  const [logs, setLogs] = useState([]);
  const [sessions, setSessions] = useState({});
  const [selectedLogIds, setSelectedLogIds] = useState([]);
  const [personas, setPersonas] = useState(null);

  const [abortController, setAbortController] = useState(null);
  const [selectedModel, setSelectedModel] = useState('gemini-3.5-flash'); // Default first choice Gemini 2.5 Flash

  // Conversation & Chat states
  const [currentConversationId, setCurrentConversationId] = useState(null);
  const [chatMessages, setChatMessages] = useState([]);
  const [isChatLoading, setIsChatLoading] = useState(false);

  // Analysis state
  const [analysisState, setAnalysisState] = useState({
    status: 'idle', // idle | parsing | searching | analyzing | complete | error
    parsingProgress: null,
    webSearch: null,
    stage1: null,
    stage2: null,
    stage3: null,
    currentStage: null,
    error: null,
    userQuery: null,
  });

  // Load initial data
  useEffect(() => {
    loadLogs();
    loadPersonas();
  }, []);

  const loadLogs = async () => {
    try {
      const data = await api.listLogs();
      setLogs(data.logs || []);
      setSessions(data.sessions || {});
    } catch (error) {
      console.error('Failed to load logs:', error);
    }
  };

  const loadPersonas = async () => {
    try {
      const data = await api.getPersonas();
      setPersonas(data);
    } catch (error) {
      console.error('Failed to load personas:', error);
    }
  };

  const handleToggleLog = (logId) => {
    setSelectedLogIds((prev) =>
      prev.includes(logId)
        ? prev.filter((id) => id !== logId)
        : [...prev, logId]
    );
  };

  const handleSelectAll = (sessionLogs) => {
    const ids = sessionLogs.map((l) => l.id);
    const allSelected = ids.every((id) => selectedLogIds.includes(id));
    if (allSelected) {
      setSelectedLogIds((prev) => prev.filter((id) => !ids.includes(id)));
    } else {
      setSelectedLogIds((prev) => [...new Set([...prev, ...ids])]);
    }
  };

  const handleStop = () => {
    if (abortController) {
      abortController.abort();
      setAbortController(null);
      setAnalysisState({
        status: 'idle',
        parsingProgress: null,
        webSearch: null,
        stage1: null,
        stage2: null,
        stage3: null,
        currentStage: null,
        error: null,
        userQuery: null,
      });
    }
  };

  const handleAnalyze = async (userQuery = null) => {
    if (selectedLogIds.length === 0) return;

    const controller = new AbortController();
    setAbortController(controller);

    setAnalysisState({
      status: 'parsing',
      parsingProgress: null,
      webSearch: null,
      stage1: null,
      stage2: null,
      stage3: null,
      currentStage: null,
      error: null,
      userQuery,
    });

    let convId = null;
    try {
      const conversation = await api.createConversation();
      convId = conversation.id;
      setCurrentConversationId(convId);
      setChatMessages([]);
    } catch (err) {
      console.error('Failed to create conversation:', err);
    }

    try {
      const initialMessage = userQuery || "Uçuş log analizi başlatıldı.";
      await api.sendMessageStream(convId, initialMessage, selectedLogIds, selectedModel, (eventType, event) => {
        switch (eventType) {
          case 'parsing_start':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'parsing',
              parsingProgress: { current: 0, total: event.total },
            }));
            break;

          case 'web_search_start':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'searching',
            }));
            break;

          case 'web_search_complete':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'analyzing',
              webSearch: {
                answer_vehicles: event.answer_vehicles,
                answer_academic: event.answer_academic,
                sources: event.sources,
                queries: event.queries,
              },
            }));
            break;

          case 'parsing_progress':
            setAnalysisState((prev) => ({
              ...prev,
              parsingProgress: {
                current: event.current,
                total: event.total,
                filename: event.filename,
                fromCache: event.from_cache,
              },
            }));
            break;

          case 'parsing_complete':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'analyzing',
              parsingProgress: { ...prev.parsingProgress, complete: true },
            }));
            break;

          case 'stage1_start':
            setAnalysisState((prev) => {
              const initialStage1 = personas?.personas?.map(p => ({
                persona_id: p.id,
                persona_name: p.name,
                persona_title: p.title,
                persona_icon: p.icon,
                persona_color: p.color,
                response: '',
                status: 'pending',
              })) || [];
              return {
                ...prev,
                status: 'analyzing',
                currentStage: 1,
                stage1: initialStage1,
              };
            });
            break;

          case 'stage1_persona_start':
            setAnalysisState((prev) => {
              const updated = prev.stage1?.map(p =>
                p.persona_id === event.persona_id ? { ...p, status: 'analyzing' } : p
              ) || [];
              return { ...prev, stage1: updated };
            });
            break;

          case 'stage1_persona_complete':
            setAnalysisState((prev) => {
              const updated = prev.stage1?.map(p =>
                p.persona_id === event.persona_id ? { ...p, ...event.data, status: 'complete' } : p
              ) || [];
              return { ...prev, stage1: updated };
            });
            break;

          case 'stage1_complete':
            setAnalysisState((prev) => ({
              ...prev,
              stage1: event.data.map(p => ({ ...p, status: 'complete' })),
              currentStage: 1,
            }));
            break;

          case 'stage2_start':
            setAnalysisState((prev) => {
              const initialStage2 = personas?.personas?.map(p => ({
                persona_id: p.id,
                persona_name: p.name,
                persona_title: p.title,
                persona_icon: p.icon,
                persona_color: p.color,
                evaluation: '',
                status: 'pending',
              })) || [];
              return {
                ...prev,
                currentStage: 2,
                stage2: initialStage2,
              };
            });
            break;

          case 'stage2_persona_start':
            setAnalysisState((prev) => {
              const updated = prev.stage2?.map(p =>
                p.persona_id === event.persona_id ? { ...p, status: 'analyzing' } : p
              ) || [];
              return { ...prev, stage2: updated };
            });
            break;

          case 'stage2_persona_complete':
            setAnalysisState((prev) => {
              const updated = prev.stage2?.map(p =>
                p.persona_id === event.persona_id ? { ...p, ...event.data, status: 'complete' } : p
              ) || [];
              return { ...prev, stage2: updated };
            });
            break;

          case 'stage2_complete':
            setAnalysisState((prev) => ({
              ...prev,
              stage2: event.data.map(p => ({ ...p, status: 'complete' })),
              currentStage: 2,
            }));
            break;

          case 'stage3_start':
            setAnalysisState((prev) => ({
              ...prev,
              currentStage: 3,
            }));
            break;

          case 'stage3_complete':
            setAnalysisState((prev) => ({
              ...prev,
              stage3: event.data,
              currentStage: 3,
            }));
            break;

          case 'report_saved':
            setAnalysisState((prev) => ({
              ...prev,
              reportSaved: {
                path: event.path,
                filename: event.filename,
                content: event.content,
              },
            }));
            break;

          case 'complete':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'complete',
            }));
            setAbortController(null);
            if (convId) {
              api.getConversation(convId).then((data) => {
                setChatMessages(data.messages || []);
              }).catch(err => console.error('Failed to fetch conversation:', err));
            }
            break;

          case 'error':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'error',
              error: event.message,
            }));
            setAbortController(null);
            break;

          default:
            console.log('Unknown event:', eventType, event);
        }
      });
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Analysis aborted by user');
        return;
      }
      setAnalysisState((prev) => ({
        ...prev,
        status: 'error',
        error: error.message,
      }));
      setAbortController(null);
    }
  };

  const handleAskQuestion = async (question) => {
    const controller = new AbortController();
    setAbortController(controller);

    setAnalysisState({
      status: 'parsing',
      parsingProgress: null,
      webSearch: null,
      stage1: null,
      stage2: null,
      stage3: null,
      currentStage: null,
      error: null,
      userQuery: question,
    });

    try {
      const logIds = selectedLogIds.length > 0 ? selectedLogIds : null;
      await api.askQuestionStream(question, logIds, selectedModel, controller.signal, (eventType, event) => {
        switch (eventType) {
          case 'parsing_start':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'parsing',
              parsingProgress: { current: 0, total: event.total },
            }));
            break;

          case 'parsing_progress':
            setAnalysisState((prev) => ({
              ...prev,
              parsingProgress: {
                current: event.current,
                total: event.total,
                filename: event.filename,
              },
            }));
            break;

          case 'parsing_complete':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'analyzing',
            }));
            break;

          case 'stage1_start':
            setAnalysisState((prev) => {
              const initialStage1 = personas?.personas?.map(p => ({
                persona_id: p.id,
                persona_name: p.name,
                persona_title: p.title,
                persona_icon: p.icon,
                persona_color: p.color,
                response: '',
                status: 'pending',
              })) || [];
              return {
                ...prev,
                status: 'analyzing',
                currentStage: 1,
                stage1: initialStage1,
              };
            });
            break;

          case 'stage1_persona_start':
            setAnalysisState((prev) => {
              const updated = prev.stage1?.map(p =>
                p.persona_id === event.persona_id ? { ...p, status: 'analyzing' } : p
              ) || [];
              return { ...prev, stage1: updated };
            });
            break;

          case 'stage1_persona_complete':
            setAnalysisState((prev) => {
              const updated = prev.stage1?.map(p =>
                p.persona_id === event.persona_id ? { ...p, ...event.data, status: 'complete' } : p
              ) || [];
              return { ...prev, stage1: updated };
            });
            break;

          case 'stage1_complete':
            setAnalysisState((prev) => ({
              ...prev,
              stage1: event.data.map(p => ({ ...p, status: 'complete' })),
            }));
            break;

          case 'stage3_start':
            setAnalysisState((prev) => ({
              ...prev,
              currentStage: 3,
            }));
            break;

          case 'stage3_complete':
            setAnalysisState((prev) => ({
              ...prev,
              stage3: event.data,
            }));
            break;

          case 'report_saved':
            setAnalysisState((prev) => ({
              ...prev,
              reportSaved: {
                path: event.path,
                filename: event.filename,
                content: event.content,
              },
            }));
            break;

          case 'complete':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'complete',
            }));
            setAbortController(null);
            break;

          case 'error':
            setAnalysisState((prev) => ({
              ...prev,
              status: 'error',
              error: event.message,
            }));
            setAbortController(null);
            break;
        }
      });
    } catch (error) {
      if (error.name === 'AbortError') {
        console.log('Question aborted by user');
        return;
      }
      setAnalysisState((prev) => ({
        ...prev,
        status: 'error',
        error: error.message,
      }));
      setAbortController(null);
    }
  };

  const handleSendChatMessage = async (content) => {
    if (!currentConversationId || !content.trim() || isChatLoading) return;

    setIsChatLoading(true);
    const newUserMsg = { role: 'user', content: content };
    setChatMessages((prev) => [...prev, newUserMsg]);

    try {
      await api.sendMessageStream(currentConversationId, content, null, selectedModel, (eventType, event) => {
        // Intermediate events are logged by api.js
      });

      const updatedConv = await api.getConversation(currentConversationId);
      setChatMessages(updatedConv.messages || []);
    } catch (err) {
      console.error('Failed to send chat message:', err);
    } finally {
      setIsChatLoading(false);
    }
  };

  const isAnalyzing = analysisState.status === 'parsing' || analysisState.status === 'analyzing';

  return (
    <div className="app">
      <LogPanel
        logs={logs}
        sessions={sessions}
        selectedLogIds={selectedLogIds}
        onToggleLog={handleToggleLog}
        onSelectAll={handleSelectAll}
        onAnalyze={handleAnalyze}
        onAskQuestion={handleAskQuestion}
        onStop={handleStop}
        isAnalyzing={isAnalyzing}
        personas={personas}
        selectedModel={selectedModel}
        setSelectedModel={setSelectedModel}
      />
      <div className="app-main">
        {analysisState.status !== 'idle' && (
          <ProgressBar analysisState={analysisState} />
        )}
        <AnalysisView
          analysisState={analysisState}
          personas={personas}
          conversationId={currentConversationId}
          chatMessages={chatMessages}
          onSendMessage={handleSendChatMessage}
          isChatLoading={isChatLoading}
        />
      </div>
    </div>
  );
}

export default App;
