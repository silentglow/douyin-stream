export interface LinkInfo {
  platform: 'douyin' | 'bilibili' | 'youtube';
  type: 'profile' | 'video' | 'up_space';
}

export function detectLinkType(rawUrl: string): LinkInfo | null {
  const lower = rawUrl.toLowerCase();

  if (lower.includes('douyin.com')) {
    if (lower.includes('/user/')) return { platform: 'douyin', type: 'profile' };
    if (lower.includes('/video/')) return { platform: 'douyin', type: 'video' };
    return null;
  }

  if (lower.includes('bilibili.com') || lower.includes('b23.tv')) {
    if (lower.includes('space.bilibili.com')) return { platform: 'bilibili', type: 'up_space' };
    return { platform: 'bilibili', type: 'video' };
  }

  if (lower.includes('youtube.com') || lower.includes('youtu.be')) {
    if (lower.includes('/channel/') || lower.includes('/c/') || lower.includes('/user/') || lower.includes('/@')) {
      return { platform: 'youtube', type: 'profile' };
    }
    return { platform: 'youtube', type: 'video' };
  }

  return null;
}

export const PLATFORM_LABEL: Record<string, string> = {
  douyin: '抖音',
  bilibili: 'B 站',
  youtube: 'YouTube',
};

export const TYPE_LABEL: Record<string, string> = {
  profile: '创作者主页',
  video: '单个视频',
  up_space: 'UP 主空间',
};
