import { useState, useRef } from 'react';
import { useTodos } from './hooks/useTodos';
import { useTheme } from './hooks/useTheme';
import { useSound } from './hooks/useSound';
import { useAchievements } from './hooks/useAchievements';
import ConfettiCanvas, { useConfetti } from './components/ConfettiCanvas';
import Header, { SearchBox } from './components/Header';
import TaskInput from './components/TaskInput';
import PrioritySelector from './components/PrioritySelector';
import FilterTabs from './components/FilterTabs';
import TaskList from './components/TaskList';
import Footer from './components/Footer';
import AchievementDrawer from './components/AchievementDrawer';
import Toast from './components/Toast';

function App() {
  const todoState = useTodos();
  const { theme, toggleTheme } = useTheme();
  const sound = useSound();
  const achievements = useAchievements(sound.playAchievement);
  const confetti = useConfetti();
  const [drawerOpen, setDrawerOpen] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleImport = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      try {
        await todoState.importTasks(file);
        alert('导入成功！');
      } catch {
        alert('导入失败：文件格式错误');
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
      {achievements.toast && (
        <Toast
          icon={achievements.toast.icon}
          title={achievements.toast.name}
          description={achievements.toast.description}
          onDismiss={achievements.dismissToast}
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
      />
      <TaskList
        tasks={todoState.tasks}
        filter={todoState.filter}
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
