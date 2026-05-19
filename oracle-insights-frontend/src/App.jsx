import React from 'react';
import Monitor from './components/Orchestration/Monitor';
import ChatBox from './components/Chat/ChatBox';
import PdfViewer from './components/Viewer/PdfViewer';
import { useOracleWorkflow } from './hooks/useOracleWorkflow';
import logoCondor from './images/logo_condor.png';
import Login from './components/Auth/Login';

function App() {

    const [plantillas, setPlantillas] = React.useState([]);

    React.useEffect(() => {
      const base = import.meta.env.VITE_API_URL || 'http://localhost:8000';
      fetch(`${base}/api/plantillas`)
        .then(res => res.ok ? res.json() : { files: [] })
        .then(data => setPlantillas(data.files || []))
        .catch(() => {});
    }, []);

    const [isAuthenticated, setIsAuthenticated] = React.useState(
        () => !!localStorage.getItem('access_token')
    );

    const {
    isAnalyzing, currentStep, agentStatuses,
    messages, pdfUrl, error, startAnalysis,
    resetWorkflow, resumeAnalysis,
    threadId
    } = useOracleWorkflow();

  if (!isAuthenticated) {
    return <Login onLogin={() => setIsAuthenticated(true)} />;
  }

  return (
    <div className="h-screen w-screen flex flex-col bg-oracle-dark overflow-hidden">
      <header className="h-14 bg-oracle-surface border-b border-oracle-border flex items-center px-4 shrink-0">
        <div className="flex items-center gap-3">
          <img src={logoCondor} alt="Logo" className="h-8 w-auto rounded-full"/>
          <h1 className="text-lg font-semibold text-oracle-text">
            Ingeniería Condor <span className="text-oracle-accent">Insights</span>
          </h1>
        </div>
        
        <div className="ml-auto flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-oracle-muted">
            <div className={`w-2 h-2 rounded-full ${isAnalyzing ? 'bg-oracle-success animate-pulse' : 'bg-oracle-muted'}`} />
            <span>{isAnalyzing ? 'Análisis en progreso' : 'Listo'}</span>
          </div>
        </div>
      </header>

      <main className="flex-1 flex overflow-hidden">
        <aside className="w-72 panel shrink-0">
          <Monitor 
            agents={agentStatuses} 
            currentStep={currentStep} 
          />
        </aside>

        <section className="flex-1 min-w-0 border-r border-oracle-border">
          <ChatBox 
            messages={messages}
            onStartAnalysis={startAnalysis}
            resumeAnalysis={resumeAnalysis}  // ← Human in the Loop
            isAnalyzing={isAnalyzing}
            threadId={threadId}
          />
        </section>

        <aside className="w-96 shrink-0">
          <PdfViewer 
            pdfUrl={pdfUrl}
            onReset={resetWorkflow}
            plantillas={plantillas}
          />
        </aside>
      </main>

      {error && (
        <div className="fixed bottom-4 right-4 bg-oracle-error text-white px-4 py-3 rounded-lg shadow-lg flex items-center gap-3 animate-slide-up">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span className="text-sm">{error}</span>
          <button 
            onClick={() => resetWorkflow()}
            className="ml-2 hover:bg-white/20 p-1 rounded"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}

export default App;
