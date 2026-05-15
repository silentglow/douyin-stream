import { apiClient } from '@/lib/api';

export interface SearchResult {
  type: 'asset' | 'creator' | 'task';
  id: string;
  title?: string;
  nickname?: string;
  description?: string;
  status?: string;
  match_type?: string;
  highlight?: string;
  creator_uid?: string;
}

export const globalSearch = async (query: string, signal?: AbortSignal): Promise<SearchResult[]> => {
  const response = await apiClient.get(`/search?q=${encodeURIComponent(query)}&limit=20`, { signal });
  return response.data.results || [];
};
