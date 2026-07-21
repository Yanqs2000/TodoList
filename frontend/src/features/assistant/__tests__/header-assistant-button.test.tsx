import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import Header from '@/features/header/components/Header';
import { I18nProvider } from '@/features/i18n/I18nProvider';

describe('Header assistant button', () => {
  it('calls onOpenAssistant', () => {
    const onOpenAssistant = vi.fn();
    render(
      <I18nProvider language="zh-CN">
        <Header
          onOpenAchievements={vi.fn()}
          onOpenCreateModal={vi.fn()}
          onOpenSettings={vi.fn()}
          onOpenAssistant={onOpenAssistant}
          muted={false}
          onToggleMuted={vi.fn()}
          onToggleLanguage={vi.fn()}
          languagePending={false}
        />
      </I18nProvider>,
    );

    fireEvent.click(screen.getByLabelText('打开 AI 助手'));

    expect(onOpenAssistant).toHaveBeenCalled();
  });
});
