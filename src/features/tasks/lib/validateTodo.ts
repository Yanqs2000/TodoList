import type { Todo, Priority, Category, TimeField } from '@/shared/types';

const VALID_PRIORITIES: Priority[] = ['low', 'medium', 'high'];
const VALID_CATEGORIES: Category[] = ['work', 'study', 'life', 'other'];
const ISO_DATETIME_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/;

function isString(v: unknown): v is string {
  return typeof v === 'string';
}

function isValidTimeField(v: unknown): v is TimeField {
  if (!v || typeof v !== 'object') return false;
  const t = v as Partial<TimeField>;
  if (!isString(t.start) || !ISO_DATETIME_RE.test(t.start)) return false;
  if (t.end !== undefined && (!isString(t.end) || !ISO_DATETIME_RE.test(t.end))) return false;
  return true;
}

export interface ValidatedTodo extends Todo {}

export function validateTodo(raw: unknown): ValidatedTodo | null {
  if (!raw || typeof raw !== 'object') return null;
  const r = raw as Record<string, unknown>;

  if (!isString(r.id) || r.id.length === 0) return null;
  if (!isString(r.text)) return null;
  if (typeof r.completed !== 'boolean') return null;
  if (!isString(r.priority) || !VALID_PRIORITIES.includes(r.priority as Priority)) return null;
  if (typeof r.createdAt !== 'number' || !Number.isFinite(r.createdAt)) return null;

  const todo: Todo = {
    id: r.id,
    text: r.text.slice(0, 500),
    completed: r.completed,
    priority: r.priority as Priority,
    createdAt: r.createdAt,
  };

  if (r.category !== undefined) {
    if (!isString(r.category) || !VALID_CATEGORIES.includes(r.category as Category)) return null;
    todo.category = r.category as Category;
  }

  if (r.time !== undefined) {
    if (!isValidTimeField(r.time)) return null;
    todo.time = r.time;
  }

  if (r.notes !== undefined) {
    if (!isString(r.notes)) return null;
    todo.notes = r.notes.slice(0, 2000);
  }

  return todo;
}

export function validateTodoArray(raw: unknown): Todo[] {
  if (!Array.isArray(raw)) return [];
  return raw.map(validateTodo).filter((t): t is Todo => t !== null);
}
