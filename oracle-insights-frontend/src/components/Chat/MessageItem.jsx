import React from 'react';
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';

const getAgentLabel = (agent) => {
  const labels = {
    supervisor: 'Supervisor',
    investigador: 'Investigador',
    analista: 'Analista',
    redactor: 'Redactor',
    system: 'Sistema',
  };
  return labels[agent?.toLowerCase()] || agent || 'Sistema';
};

const getAgentColor = (agent) => {
  const colors = {
    supervisor: 'bg-oracle-accent',
    investigador: 'bg-oracle-success',
    analista: 'bg-oracle-warning',
    redactor: 'bg-oracle-primary',
    system: 'bg-oracle-muted',
  };
  return colors[agent?.toLowerCase()] || 'bg-oracle-muted';
};

const MessageItem = ({ message }) => {
  const isUser = message.agent === 'user';
  const isSystem = message.agent === 'system';

  const formatTime = (timestamp) => {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('es-MX', { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
  };

if (message.type === "screenshots") {
  return (
    <div className="flex justify-start animate-in">
      <div className="bg-oracle-border text-oracle-muted rounded-lg p-3 w-full">
        <p className="text-sm text-center mb-2">{message.content}</p>
        <div className="flex flex-wrap gap-3 justify-center">
          {message.screenshots?.map((url, i) => (
            <div key={i} className="flex flex-col items-center gap-1">
                <img
                  src={`${API_BASE_URL}${url}`}
                  alt={`Captura ${i + 1}`}
                  className="w-24 h-24 object-cover rounded border border-oracle-border cursor-pointer"
                />
                <a
                  href={`${API_BASE_URL}${url}`}
                  download={`captura_${i + 1}.jpg`}   // ← cambiar a .jpg
                  className="text-xs text-oracle-accent underline"
                >
                Descargar {i + 1}
              </a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

  return (
    <div 
      className={`
        animate-in
        ${isUser ? 'flex justify-end' : 'flex justify-start'}
      `}
    >
      <div 
        className={`
          max-w-[80%] rounded-lg p-3
          ${isUser 
            ? 'bg-oracle-accent text-white' 
            : isSystem
              ? 'bg-oracle-border text-oracle-muted text-center w-full max-w-full'
              : 'bg-oracle-surface border border-oracle-border'
          }
        `}
      >
        {!isUser && !isSystem && (
          <div className="flex items-center gap-2 mb-1">
            <div className={`w-5 h-5 rounded-full ${getAgentColor(message.agent)} flex items-center justify-center text-[10px] font-bold text-white`}>
              {getAgentLabel(message.agent).charAt(0)}
            </div>
            <span className="text-xs font-medium text-oracle-accent">
              {getAgentLabel(message.agent)}
            </span>
          </div>
        )}
        
        <p className={`text-sm ${isUser ? 'text-white' : 'text-oracle-text'} whitespace-pre-wrap`}>
          {message.content}
        </p>
        
        <span className={`text-[10px] mt-1 block ${isUser ? 'text-white/70' : 'text-oracle-muted'}`}>
          {formatTime(message.timestamp)}
        </span>
      </div>
    </div>
  );
};

export default MessageItem;
