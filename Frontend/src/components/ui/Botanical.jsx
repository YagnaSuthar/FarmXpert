// Decorative leaf artwork (the Aaurawell botanical set in /public/images/botanical).
// Artwork grows from its bottom-left corner; mirror with -scale-x-100 / -scale-y-100
// to anchor it to other corners. Purely decorative: hidden from screen readers.

import Image from 'next/image';

import { cn } from '@/lib/cn';

const ART = {
  fern: { src: '/images/botanical/fern.svg', width: 410, height: 570 },
  eucalyptus: { src: '/images/botanical/eucalyptus.svg', width: 430, height: 530 },
  olive: { src: '/images/botanical/olive-twig.svg', width: 490, height: 350 },
  tropical: { src: '/images/botanical/tropical-leaf.svg', width: 470, height: 510 },
  corner: { src: '/images/botanical/leaves-corner.svg', width: 440, height: 440 },
  sprig: { src: '/images/botanical/leaf-branch.svg', width: 320, height: 520 },
  leaf: { src: '/images/botanical/leaf-single.svg', width: 140, height: 140 },
  leafLight: { src: '/images/botanical/leaf-single-light.svg', width: 140, height: 140 },
};

export default function Botanical({ name, className, priority = false }) {
  const { src, width, height } = ART[name];
  return (
    <Image
      src={src}
      alt=""
      aria-hidden
      width={width}
      height={height}
      priority={priority}
      className={cn('pointer-events-none absolute h-auto select-none', className)}
    />
  );
}
