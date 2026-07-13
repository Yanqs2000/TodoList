import { render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';
import App from '../App';

describe('App startup gate', () => {
  beforeEach(() => {
    Reflect.deleteProperty(window, '__TAURI_INTERNALS__');
  });

  it('does not mount the todo application in an ordinary browser', () => {
    render(<App />);

    expect(screen.getByRole('heading')).toHaveTextContent('请通过桌面应用运行');
    expect(document.querySelector('.app-shell')).not.toBeInTheDocument();
  });
});
