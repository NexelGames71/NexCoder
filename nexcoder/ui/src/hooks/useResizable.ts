import { useCallback, useRef, useEffect } from 'react';

type Direction = 'horizontal' | 'vertical';

interface UseResizableOptions {
  direction: Direction;
  initialSize: number;
  minSize: number;
  maxSize: number;
  /** If true, dragging right/down increases size. If false, dragging right/down decreases size. */
  reverse?: boolean;
  onResize?: (newSize: number) => void;
  onResizeEnd?: (newSize: number) => void;
}

export function useResizable({
  direction,
  initialSize,
  minSize,
  maxSize,
  reverse = false,
  onResize,
  onResizeEnd,
}: UseResizableOptions) {
  const sizeRef = useRef(initialSize);
  const isDragging = useRef(false);
  const startPos = useRef(0);
  const startSize = useRef(0);
  const handleRef = useRef<HTMLDivElement | null>(null);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      e.stopPropagation();
      isDragging.current = true;
      startPos.current = direction === 'horizontal' ? e.clientX : e.clientY;
      startSize.current = sizeRef.current;

      // Add active class to handle
      if (handleRef.current) {
        handleRef.current.classList.add('active');
      }

      // Prevent text selection during drag
      document.body.style.cursor = direction === 'horizontal' ? 'col-resize' : 'row-resize';
      document.body.style.userSelect = 'none';

      const handleMouseMove = (moveEvent: MouseEvent) => {
        if (!isDragging.current) return;

        const currentPos = direction === 'horizontal' ? moveEvent.clientX : moveEvent.clientY;
        const delta = currentPos - startPos.current;
        const multiplier = reverse ? -1 : 1;
        let newSize = startSize.current + delta * multiplier;

        // Clamp
        newSize = Math.max(minSize, Math.min(maxSize, newSize));
        sizeRef.current = newSize;
        onResize?.(newSize);
      };

      const handleMouseUp = () => {
        isDragging.current = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';

        if (handleRef.current) {
          handleRef.current.classList.remove('active');
        }

        onResizeEnd?.(sizeRef.current);
        document.removeEventListener('mousemove', handleMouseMove);
        document.removeEventListener('mouseup', handleMouseUp);
      };

      document.addEventListener('mousemove', handleMouseMove);
      document.addEventListener('mouseup', handleMouseUp);
    },
    [direction, minSize, maxSize, reverse, onResize, onResizeEnd]
  );

  return { handleMouseDown, handleRef, sizeRef };
}
