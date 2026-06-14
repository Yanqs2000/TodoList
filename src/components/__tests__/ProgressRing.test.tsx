import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import ProgressRing from '../ProgressRing';

describe('ProgressRing', () => {
  it('should display current/goal text', () => {
    render(<ProgressRing current={5} goal={10} />);
    expect(screen.getByText('5/10')).toBeInTheDocument();
  });

  it('should render SVG circle', () => {
    const { container } = render(<ProgressRing current={5} goal={10} />);
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();
  });

  it('should cap progress at 100%', () => {
    const { container } = render(<ProgressRing current={15} goal={10} />);
    const fillCircle = container.querySelector('.progress-ring-fill');
    const offset = fillCircle?.getAttribute('stroke-dashoffset');
    expect(offset).toBe('0');
  });
});
