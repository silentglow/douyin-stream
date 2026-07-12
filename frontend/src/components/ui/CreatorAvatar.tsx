import { useState } from 'react';
import { avatarGradient, initialOf, platformColor, platformLabel } from '@/lib/format';
import { cn } from '@/lib/utils';

interface CreatorAvatarProps {
  name?: string | null;
  avatar?: string | null;
  platform?: string;
  seed?: string;
  size?: number;
  /** Show a thin ring tinted with the platform color. */
  ring?: boolean;
  className?: string;
}

/**
 * Vivid, deterministic creator avatar. Uses the remote image when present,
 * otherwise falls back to a per-seed gradient with the name's initial —
 * giving every row a stable color anchor even when stats are empty.
 */
export function CreatorAvatar({
  name,
  avatar,
  platform,
  seed,
  size = 34,
  ring = true,
  className,
}: CreatorAvatarProps) {
  const [broken, setBroken] = useState(false);
  const key = seed || name || 'creator';
  const showImg = avatar && !broken;
  const pColor = platformColor(platform);

  return (
    <span
      className={cn('relative inline-flex shrink-0 items-center justify-center', className)}
      style={{ width: size, height: size }}
      title={name ? `${name} · ${platformLabel(platform)}` : undefined}
    >
      <span
        className="relative flex items-center justify-center overflow-hidden rounded-full text-white font-semibold"
        style={{
          width: size,
          height: size,
          fontSize: size * 0.42,
          background: avatarGradient(key),
          boxShadow: ring ? `0 0 0 1.5px var(--color-paper), 0 0 0 3px ${pColor}55` : undefined,
        }}
      >
        {/* initial always sits underneath — visible if the remote image is transparent/blocked */}
        <span className="absolute inset-0 flex items-center justify-center">{initialOf(name)}</span>
        {showImg && (
          <img
            src={avatar as string}
            alt={name || ''}
            loading="lazy"
            className="relative h-full w-full object-cover"
            onError={() => setBroken(true)}
          />
        )}
      </span>
      {/* platform dot */}
      <span
        className="absolute -bottom-0.5 -right-0.5 rounded-full border border-[var(--color-paper)]"
        style={{ width: size * 0.3, height: size * 0.3, background: pColor }}
      />
    </span>
  );
}
