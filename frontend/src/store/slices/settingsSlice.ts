import type { StateCreator } from 'zustand';
import { getSettings } from '@/lib/api';
import type { StoreState } from '../useStore';

export type SettingsPayload = Awaited<ReturnType<typeof getSettings>>;

export interface SettingsSlice {
  settings: SettingsPayload | null;
  _fetchingSettings: Promise<SettingsPayload | undefined> | null;
  fetchSettings: () => Promise<SettingsPayload | undefined>;
}

export const createSettingsSlice: StateCreator<StoreState, [], [], SettingsSlice> = (set, get) => ({
  settings: null,
  _fetchingSettings: null,
  fetchSettings: async () => {
    const { _fetchingSettings } = get();
    if (_fetchingSettings) return _fetchingSettings;
    const promise = (async () => {
      try {
        const data = await getSettings();
        if (data && typeof data === 'object' && 'status_summary' in data) {
          set({ settings: data, _fetchingSettings: null });
          return data;
        } else {
          console.error('getSettings returned invalid data:', data);
          set({ _fetchingSettings: null });
          return undefined;
        }
      } catch (error) {
        console.error('Failed to fetch settings', error);
        set({ _fetchingSettings: null });
        return undefined;
      }
    })();
    set({ _fetchingSettings: promise });
    return promise;
  },
});
