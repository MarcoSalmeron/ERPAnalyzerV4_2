import { useState, useEffect, useRef, useCallback } from 'react';
import { createAnalysis, getWebSocketUrl, api } from '../api/apiConfig';

export const AGENTS = [
  { id: 1, name: 'Supervisor', icon: 'S', color: 'bg-oracle-accent' },
  { id: 2, name: 'Investigador', icon: 'I', color: 'bg-oracle-success' },
  { id: 3, name: 'Analista', icon: 'A', color: 'bg-oracle-warning' },
  { id: 4, name: 'Redactor', icon: 'R', color: 'bg-oracle-primary' },
];

export const useOracleWorkflow = () => {
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [agentStatuses, setAgentStatuses] = useState(
    AGENTS.map(agent => ({ ...agent, status: 'waiting', log: '' }))
  );
  const [messages, setMessages] = useState([]);
  const [pdfUrl, setPdfUrl] = useState(null);
  const [error, setError] = useState(null);
  const wsRef = useRef(null);
  const threadIdRef = useRef(null);

  //  función para reanudar
async function resumeAnalysis(respuesta) {
  console.log('🔄 resumeAnalysis llamado con:', respuesta);
  if (!threadIdRef.current) {
    console.error('❌ No threadIdRef.current');
    return;
  }
  setIsAnalyzing(true);

  try {
    // Endpoint para ranudar el flujo
    const response = await api.post(`/impact/resume/${threadIdRef.current}`, {
      erp_module: respuesta
    });
    console.log('✅ Respuesta del endpoint:', response.status);
  } catch (error) {
    console.error('❌ Error en resumeAnalysis:', error);
  }
}

  const connectWebSocket = useCallback((threadId) => {
    const wsUrl = getWebSocketUrl(threadId);
    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      console.log('WebSocket connected');
    };

    wsRef.current.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        handleWebSocketMessage(data);
      } catch (err) {
        console.error('Error parsing WebSocket message:', err);
      }
    };

    wsRef.current.onerror = (err) => {
      console.error('WebSocket error:', err);
      setError('Error de conexión');
    };

    wsRef.current.onclose = () => {
      console.log('WebSocket disconnected');
      // intentar reconectar si threadIdRef.current existe
      setTimeout(() => {
        if (threadIdRef.current) connectWebSocket(threadIdRef.current);
      }, 1000);
    };
  }, []);

  const handleWebSocketMessage = useCallback((data) => {
   console.log('📨 Mensaje recibido:', data);

  const { step, agent, status, content, log, pdf_ready, pdf_url } = data;

  if (data.error) {
    setError(data.error);
    setIsAnalyzing(false);
    return;
  }

  if (content && agent === 'supervisor') {
    setIsAnalyzing(false);
  }

    if (data.type === "chat") {
  setIsAnalyzing(false);  // Habilitar el input
  setMessages(prev => [...prev, {
    id: Date.now(),
    agent: data.agent || 'supervisor',
    content: data.content,
    timestamp: new Date().toISOString(),
  }]);
  return;
}

    if (data.type === "error") {
  setIsAnalyzing(false);
  setMessages(prev => [...prev, {
    id: Date.now(),
    agent: "system",
    type: "error",          // componente de chat renderizarlo en rojo  
    content: data.content,
    timestamp: new Date().toISOString(),
  }]);
  return;
}

    // interrupción
if (data.type === "interrupt") {
  setIsAnalyzing(false);
  const contenidoModulo = "Los módulos ERP disponibles son:";
  const displayContent = data.content.includes(contenidoModulo)
    ? "Esperando Modulo ERP..."
    : data.content;

  setMessages(prev => [...prev, {
    id: Date.now(),
    agent: "system",
    type: "interrupt",
    content: displayContent,
    timestamp: new Date().toISOString(),
  }]);
  return;
}

if (data.type === "info") {
  setIsAnalyzing(false);
  setMessages(prev => [...prev, {
    id: Date.now(),
    agent: "system",
    type: "info",
    content: data.content,
    timestamp: new Date().toISOString(),
  }]);
  return;
}

    if (step) {
      setCurrentStep(step);
      setAgentStatuses(prev =>
        prev.map(a => {
          if (a.id === step) {
            return { ...a, status: status || 'active', log: log || '' };
          }
          if (a.id < step) {
            return { ...a, status: 'completed', log: 'Completado' };
          }
          return a;
        })
      );
    }

    if (content) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        agent: agent || 'system',
        content,
        timestamp: new Date().toISOString(),
      }]);
    }

    if (pdf_ready && pdf_url) {
      setPdfUrl(pdf_url);
      setIsAnalyzing(false);
      setAgentStatuses(prev =>
        prev.map(a => ({ ...a, status: 'completed', log: 'Completado' }))
      );
    }
  }, []);

  const startAnalysis = useCallback(async (query) => {
    setIsAnalyzing(true);
    setError(null);
    setPdfUrl(null);
    setCurrentStep(0);
    setAgentStatuses(AGENTS.map(agent => ({ ...agent, status: 'waiting', log: '' })));

    setMessages(prev => [
      ...prev,
      { id: Date.now(), agent: 'user', content: query, timestamp: new Date().toISOString() },
      { id: Date.now() + 1, agent: 'system', content: 'Conectando con el agente...', timestamp: new Date().toISOString() }
    ]);

    try {
      const response = await createAnalysis(query, threadIdRef.current);
      const { thread_id } = response;
      threadIdRef.current = thread_id;
      connectWebSocket(thread_id);

      setMessages(prev => [...prev, {
      id: Date.now() + 2,
      agent: 'system',
      content: 'Agente conectado.',
      timestamp: new Date().toISOString(),
        }]);
    } catch (err) {
      setError(err.response?.data?.detail || 'Error al iniciar el análisis');
      setIsAnalyzing(false);
    }
  }, [connectWebSocket]);

  const resetWorkflow = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
    }
    setIsAnalyzing(false);
    setCurrentStep(0);
    setAgentStatuses(AGENTS.map(agent => ({ ...agent, status: 'waiting', log: '' })));
    setMessages([]);
    setPdfUrl(null);
    setError(null);
    threadIdRef.current = null;
  }, []);

  useEffect(() => {
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  return {
    isAnalyzing,
    currentStep,
    agentStatuses,
    messages,
    pdfUrl,
    error,
    startAnalysis,
    resetWorkflow,
    resumeAnalysis, // Reanudar Flujo
  };
};
