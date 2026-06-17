import { useState, useRef } from 'react';
import { useTodos } from '@/features/tasks/hooks/useTodos';
import { useTheme } from '@/features/theme/hooks/useTheme';
import { useSound } from '@/features/sound/hooks/useSound';
import { useAchievements } from '@/features/achievements/hooks/useAchievements';
import ConfettiCanvas, { useConfetti } from '@/features/confetti/components/ConfettiCanvas';
import Header, { SearchBox } from '@/features/header/components/Header';
import TaskInput from '@/features/tasks/components/TaskInput';
import PrioritySelector from '@/features/tasks/components/PrioritySelector';
import FilterTabs from '@/features/tasks/components/FilterTabs';
import TaskList from '@/features/tasks/components/TaskList';
import Footer from '@/features/stats/components/Footer';
import AchievementDrawer from '@/features/achievements/components/AchievementDrawer';
import Toast from '@/features/achievements/components/Toast';
import InfoToast from '@/features/feedback/components/InfoToast';
import './styles/App.css';

interface InfoToastState {
  message: string;
  tone: 'success' | 'error';
}

function App() {
  const todoState = useTodos();
  const { theme, toggleTheme } = useTheme();
  const sound = useSound();
  const achievements = useAchievements(sound.playAchievement);
  const confetti = useConfetti();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [infoToast, setInfoToast] = useState<InfoToastState | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const infoTimerRef = useRef<number | null>(null);

  const showInfo = (message: string, tone: 'success' | 'error') => {
    setInfoToast({ message, tone });
    if (infoTimerRef.current !== null) clearTimeout(infoTimerRef.current);
    infoTimerRef.current = window.setTimeout(() => setInfoToast(null), 2500);
  };

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      try {
        const result = await todoState.importTasks(file);
        if (result.added === 0) {
          showInfo('没有可导入的任务（已存在或格式无效）', 'error');
        } else {
          const extra = result.skipped > 0 ? `，跳过 ${result.skipped} 个无效项` : '';
          showInfo(`已导入 ${result.added} 个任务${extra}`, 'success');
        }
      } catch {
        showInfo('导入失败：文件格式错误', 'error');
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  return (
    <div className="container">
      <input
        ref={fileInputRef}
        type="file"
        accept=".json"
        style={{ display: 'none' }}
        onChange={handleFileChange}
      />
      <AchievementDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        achievements={achievements.achievements}
        allAchievements={achievements.allAchievements}
      />
      <div className="sr-only" role="status" aria-live="polite">
        {achievements.toast ? `成就解锁：${achievements.toast.name} — ${achievements.toast.description}` : ''}
        {infoToast ? infoToast.message : ''}
      </div>
      {achievements.toast && (
        <Toast
          icon={achievements.toast.icon}
          title={achievements.toast.name}
          description={achievements.toast.description}
          onDismiss={achievements.dismissToast}
        />
      )}
      {infoToast && (
        <InfoToast
          message={infoToast.message}
          tone={infoToast.tone}
          onDismiss={() => setInfoToast(null)}
        />
      )}
      <ConfettiCanvas canvasRef={confetti.canvasRef} />
      <Header
        theme={theme}
        onToggleTheme={toggleTheme}
        onOpenAchievements={() => setDrawerOpen(true)}
        muted={sound.muted}
        onToggleMuted={sound.toggleMuted}
        onExport={todoState.exportTasks}
        onImport={handleImport}
      />
      <SearchBox value={todoState.searchQuery} onChange={todoState.setSearchQuery} />
      <TaskInput addTask={todoState.addTask} />
      <PrioritySelector
        priority={todoState.priority}
        setPriority={todoState.setPriority}
      />
      <FilterTabs
        filter={todoState.filter}
        setFilter={todoState.setFilter}
        categoryFilter={todoState.categoryFilter}
        setCategoryFilter={todoState.setCategoryFilter}
        categories={todoState.categories}
        categoryLabels={todoState.categoryLabels}
      />
      <TaskList
        tasks={todoState.tasks}
        filter={todoState.filter}
        sortMode={todoState.sortMode}
        onToggleSortMode={todoState.setSortMode}
        onToggle={(id) => {
          const task = todoState.allTasks.find(t => t.id === id);
          todoState.toggleTask(id);
          if (task && !task.completed) {
            achievements.recordCompletion();
            sound.playComplete();
            const el = document.querySelector(`[data-task-id="${id}"]`);
            if (el) {
              const rect = el.getBoundingClientRect();
              confetti.burst(rect.left + rect.width / 2, rect.top + rect.height / 2);
            }
          }
        }}
        onDelete={(id) => {
          sound.playDelete();
          todoState.removeTask(id);
        }}
        onEdit={todoState.editTask}
        onReorder={todoState.reorderTasks}
      />
      <Footer
        stats={todoState.stats}
        onClearCompleted={todoState.clearCompleted}
        achievements={achievements.achievements}
      />
    </div>
  );
}

export default App;
