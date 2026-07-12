/** Relative / short date helpers for library & task UI. */

export function formatLastSync(iso: string | null | undefined): string {
  if (!iso) return '从未同步';
  const t = Date.parse(iso);
  if (Number.isNaN(t)) return '从未同步';
  const diffMs = Date.now() - t;
  if (diffMs < 0) return '刚刚';
  const mins = Math.floor(diffMs / 60_000);
  if (mins < 1) return '刚刚';
  if (mins < 60) return `${mins} 分钟前`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} 小时前`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${days} 天前`;
  return new Date(t).toLocaleDateString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' });
}

export function platformLabel(platform?: string): string {
  switch ((platform || '').toLowerCase()) {
    case 'bilibili':
      return 'B站';
    case 'youtube':
      return 'YouTube';
    case 'local':
      return '本地';
    case 'douyin':
    default:
      return '抖音';
  }
}

/** Brand accent per platform — used for badges & avatar rings. */
export function platformColor(platform?: string): string {
  switch ((platform || '').toLowerCase()) {
    case 'bilibili':
      return '#fb7299';
    case 'youtube':
      return '#ff4d4d';
    case 'local':
      return '#8e8e93';
    case 'douyin':
    default:
      return '#fe2c55';
  }
}

/** Deterministic vivid gradient for avatar fallbacks — high-energy, stable per seed. */
export function avatarGradient(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i += 1) {
    h = (h * 31 + seed.charCodeAt(i)) % 360;
  }
  const h2 = (h + 42) % 360;
  return `linear-gradient(135deg, hsl(${h} 72% 56%), hsl(${h2} 74% 48%))`;
}

/** First visible glyph of a name, for avatar initials. */
export function initialOf(name?: string | null): string {
  const trimmed = (name || '').trim();
  if (!trimmed) return '?';
  return Array.from(trimmed)[0].toUpperCase();
}

/** FULL sync is destructive relative to archive workflow — always confirm. */
export const FULL_SYNC_CONFIRM =
  '全量重拉会忽略「已收录历史」去重策略，重新下载该创作者的全部视频（包括你已归档/移走的内容）。\n\n' +
  '日常请用「同步」：只拉取上次同步之后的新视频，本地文件缺失也不会自动重下历史。\n\n' +
  '确定仍要全量重拉吗？';

/** Resolve a platform profile URL for a creator (Douyin / Bilibili / YouTube). */
export function resolveCreatorHomepage(creator: {
  homepage_url?: string | null;
  platform?: string | null;
  sec_user_id?: string | null;
  uid?: string | null;
}): string | null {
  const direct = (creator.homepage_url || '').trim();
  if (direct.startsWith('http://') || direct.startsWith('https://')) return direct;

  const platform = (creator.platform || 'douyin').toLowerCase();
  const sec = (creator.sec_user_id || '').trim();
  const uid = (creator.uid || '').trim();

  if (platform === 'bilibili') {
    const mid = sec || uid.replace(/^bilibili:/i, '');
    if (mid) return `https://space.bilibili.com/${mid}`;
  }
  if (platform === 'youtube') {
    const channelId = sec || uid.replace(/^youtube:/i, '');
    if (channelId.startsWith('UC') || channelId.startsWith('@')) {
      return channelId.startsWith('@')
        ? `https://www.youtube.com/${channelId}`
        : `https://www.youtube.com/channel/${channelId}`;
    }
    if (channelId) return `https://www.youtube.com/channel/${channelId}`;
  }
  // douyin default
  const secUid = sec.startsWith('MS4w') ? sec : '';
  if (secUid) return `https://www.douyin.com/user/${secUid}`;
  if (uid && !uid.includes(':')) return `https://www.douyin.com/user/${uid}`;

  return null;
}

export function openCreatorHomepage(creator: {
  homepage_url?: string | null;
  platform?: string | null;
  sec_user_id?: string | null;
  uid?: string | null;
}): boolean {
  const url = resolveCreatorHomepage(creator);
  if (!url) return false;
  window.open(url, '_blank', 'noopener,noreferrer');
  return true;
}
