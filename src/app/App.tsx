import { useState, useRef, useEffect, useCallback } from 'react';
import type { TimeField, Category, Priority } from '@/shared/types';
import { DAILY_GOAL } from '@/shared/constants';
import { useTodos } from '@/features/tasks/hooks/useTodos';
import { useTheme } from '@/features/theme/hooks/useTheme';
import { useSound } from '@/features/sound/hooks/useSound';
import { useAchievements } from '@/features/achievements/hooks/useAchievements';
import ConfettiCanvas, { useConfetti } from '@/features/confetti/components/ConfettiCanvas';
import Header from '@/features/header/components/Header';
import TaskList from '@/features/tasks/components/TaskList';
import Footer from '@/features/stats/components/Footer';
import AchievementDrawer from '@/features/achievements/components/AchievementDrawer';
import Toast from '@/features/achievements/components/Toast';
import InfoToast from '@/features/feedback/components/InfoToast';
import Sidebar from '@/features/tasks/components/Sidebar';
import DetailPanel from '@/features/tasks/components/DetailPanel';
import ThemeSwitcher from '@/features/theme/components/ThemeSwitcher';
import CreateTaskModal from '@/features/tasks/components/CreateTaskModal';
import './styles/App.css';

interface InfoToastState {
  message: string;
  tone: 'success' | 'error';
}



function App() {
  const todoState = useTodos();
  const { theme, setTheme } = useTheme();
  const sound = useSound();
  const achievements = useAchievements(sound.playAchievement);
  const confetti = useConfetti();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [themeSwitcherOpen, setThemeSwitcherOpen] = useState(false);
  const [createModalOpen, setCreateModalOpen] = useState(false);
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null);
  const [infoToast, setInfoToast] = useState<InfoToastState | null>(null);
  const infoTimerRef = useRef<number | null>(null);

  const showInfo = (message: string, tone: 'success' | 'error') => {
    setInfoToast({ message, tone });
    if (infoTimerRef.current !== null) clearTimeout(infoTimerRef.current);
    infoTimerRef.current = window.setTimeout(() => setInfoToast(null), 2500);
  };

  // Cmd+N shortcut for opening create task modal
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'n') {
        e.preventDefault();
        setCreateModalOpen(true);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  const handleToggle = useCallback((id: string) => {
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
  }, [todoState, achievements, sound, confetti]);

  const handleDelete = useCallback((id: string) => {
    sound.playDelete();
    todoState.removeTask(id);
    if (selectedTaskId === id) setSelectedTaskId(null);
  }, [todoState, sound, selectedTaskId]);

  const handleSelectTask = useCallback((id: string | null) => {
    setSelectedTaskId(id);
  }, []);

  const handleAddTask = useCallback((text: string, time?: TimeField, category?: Category, priority?: Priority, notes?: string) => {
    todoState.addTask(text, time, category, notes, priority);
    setCreateModalOpen(false);
  }, [todoState]);

  const handleClearCompleted = useCallback(() => {
    const count = todoState.stats.completed;
    if (count === 0) return;
    todoState.clearCompleted();
    showInfo(`已清除 ${count} 个已完成任务`, 'success');
  }, [todoState]);

  const selectedTask = selectedTaskId
    ? todoState.allTasks.find(t => t.id === selectedTaskId) ?? null
    : null;

  return (
    <div className="app-shell">
      <AchievementDrawer
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        achievements={achievements.achievements}
        allAchievements={achievements.allAchievements}
      />

      <ThemeSwitcher
        open={themeSwitcherOpen}
        currentTheme={theme}
        onClose={() => setThemeSwitcherOpen(false)}
        onSelect={(id) => {
          setTheme(id);
          setThemeSwitcherOpen(false);
        }}
      />

      <CreateTaskModal
        open={createModalOpen}
        onClose={() => setCreateModalOpen(false)}
        onAdd={handleAddTask}
        defaultPriority={todoState.priority}
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

      <div className="app-shell__header">
        <Header
          theme={theme}
          onOpenThemeSwitcher={() => setThemeSwitcherOpen(true)}
          onOpenAchievements={() => setDrawerOpen(true)}
          onOpenCreateModal={() => setCreateModalOpen(true)}
          muted={sound.muted}
          onToggleMuted={sound.toggleMuted}
        />
      </div>

      <aside className="app-shell__sidebar">
        <Sidebar
          categories={todoState.categories}
          categoryLabels={todoState.categoryLabels}
          categoryFilter={todoState.categoryFilter}
          setCategoryFilter={todoState.setCategoryFilter}
          filter={todoState.filter}
          setFilter={todoState.setFilter}
          stats={todoState.stats}
          todayCompleted={achievements.achievements.todayCompleted}
          dailyGoal={DAILY_GOAL}
          searchQuery={todoState.searchQuery}
          setSearchQuery={todoState.setSearchQuery}
        />
      </aside>

      <main className="app-shell__list">
        <TaskList
          tasks={todoState.tasks}
          filter={todoState.filter}
          sortMode={todoState.sortMode}
          onToggleSortMode={todoState.setSortMode}
          onToggle={handleToggle}
          onDelete={handleDelete}
          onEdit={todoState.editTask}
          onReorder={todoState.reorderTasks}
          selectedTaskId={selectedTaskId}
          onSelectTask={handleSelectTask}
        />
        <Footer
          stats={todoState.stats}
          onClearCompleted={handleClearCompleted}
          achievements={achievements.achievements}
        />
      </main>

      <aside className="app-shell__detail">
        <DetailPanel
          selectedTask={selectedTask}
          onEdit={todoState.editTask}
          onToggle={handleToggle}
          onDelete={handleDelete}
          onClose={() => setSelectedTaskId(null)}
          stats={todoState.stats}
          todayCompleted={achievements.achievements.todayCompleted}
          dailyGoal={DAILY_GOAL}
          streakDays={achievements.achievements.streakDays}
        />
      </aside>
    </div>
  );
}

export default App;
