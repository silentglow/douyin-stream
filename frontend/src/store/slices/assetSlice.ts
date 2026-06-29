import type { StateCreator } from 'zustand';
import type { Asset } from '@/lib/api';
import { getAssets } from '@/lib/api';
import type { StoreState } from '../useStore';

const ASSETS_CACHE_TTL = 30_000;

export interface AssetSlice {
  assets: Asset[];
  assetsLoadedAt: number;
  fetchAssets: (force?: boolean) => Promise<Asset[]>;
  _fetchingAssets: Promise<Asset[]> | null;
}

export const createAssetSlice: StateCreator<StoreState, [], [], AssetSlice> = (set, get) => ({
  assets: [],
  assetsLoadedAt: 0,
  _fetchingAssets: null,
  fetchAssets: async (force = false) => {
    const { assetsLoadedAt, assets, _fetchingAssets } = get();
    if (!force && assetsLoadedAt > 0 && Date.now() - assetsLoadedAt < ASSETS_CACHE_TTL) {
      return assets;
    }
    if (_fetchingAssets) return _fetchingAssets;
    const promise = (async () => {
      try {
        const data = await getAssets();
        if (Array.isArray(data)) {
          set({ assets: data, assetsLoadedAt: Date.now(), _fetchingAssets: null });
          return data;
        } else {
          console.error('getAssets returned non-array data:', data);
          set({ _fetchingAssets: null });
          return get().assets;
        }
      } catch (error) {
        console.error('Failed to fetch assets', error);
        set({ _fetchingAssets: null });
        return get().assets;
      }
    })();
    set({ _fetchingAssets: promise });
    return promise;
  },
});
