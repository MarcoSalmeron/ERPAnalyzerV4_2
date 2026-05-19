import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const WS_BASE_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000';

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const API_ENDPOINTS = {
  analyze: '/impact/analyze',
};

export const getWebSocketUrl = (threadId) => `${WS_BASE_URL}/impact/ws/${threadId}`;

export const createAnalysis = async (query) => {
  const response = await api.post(API_ENDPOINTS.analyze, { query });
  return response.data;
};
