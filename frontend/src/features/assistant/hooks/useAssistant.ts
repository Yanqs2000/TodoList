import { useCallback, useEffect, useRef, useState } from 'react';
import type {
  AssistantAttachment,
  AssistantConversationSummary,
  AssistantMessage,
  AssistantProposal,
  AssistantSettingsPatch,
  AssistantSettingsView,
  ResolveProposalResult,
  TodoApi,
} from '@/shared/api/contracts';

export interface AssistantState {
  conversations: AssistantConversationSummary[];
  activeId: string | null;
  messages: AssistantMessage[];
  proposals: AssistantProposal[];
  settingsView: AssistantSettingsView | null;
  sending: boolean;
  selectConversation: (id: string) => Promise<void>;
  startNewConversation: () => void;
  deleteConversation: (id: string) => Promise<void>;
  send: (content: string, attachments: AssistantAttachment[]) => Promise<void>;
  retry: () => Promise<void>;
  resolveProposal: (
    id: string,
    action: 'accept' | 'reject',
  ) => Promise<ResolveProposalResult | undefined>;
  saveSettings: (patch: AssistantSettingsPatch) => Promise<boolean>;
}

export function useAssistant(
  api: TodoApi,
  onError: (error: unknown) => void,
): AssistantState {
  const [conversations, setConversations] = useState<AssistantConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [proposals, setProposals] = useState<AssistantProposal[]>([]);
  const [settingsView, setSettingsView] = useState<AssistantSettingsView | null>(null);
  const [sending, setSending] = useState(false);
  const lastSendRef = useRef<{ content: string; attachments: AssistantAttachment[] } | null>(null);
  const apiRef = useRef(api);
  const onErrorRef = useRef(onError);
  apiRef.current = api;
  onErrorRef.current = onError;

  const selectConversation = useCallback(async (id: string) => {
    try {
      const detail = await apiRef.current.getAssistantConversation(id);
      setActiveId(id);
      setMessages(detail.messages);
      setProposals(detail.proposals);
    } catch (error) {
      onErrorRef.current(error);
    }
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        const [view, list] = await Promise.all([
          apiRef.current.getAssistantSettings(),
          apiRef.current.listAssistantConversations(),
        ]);
        setSettingsView(view);
        setConversations(list);
        if (list.length > 0) await selectConversation(list[0].id);
      } catch (error) {
        onErrorRef.current(error);
      }
    })();
  }, [selectConversation]);

  const startNewConversation = useCallback(() => {
    setActiveId(null);
    setMessages([]);
    setProposals([]);
  }, []);

  const deleteConversation = useCallback(async (id: string) => {
    try {
      await apiRef.current.deleteAssistantConversation(id);
      const list = await apiRef.current.listAssistantConversations();
      setConversations(list);
      if (activeId === id) {
        if (list.length > 0) await selectConversation(list[0].id);
        else startNewConversation();
      }
    } catch (error) {
      onErrorRef.current(error);
    }
  }, [activeId, selectConversation, startNewConversation]);

  const send = useCallback(async (content: string, attachments: AssistantAttachment[]) => {
    setSending(true);
    lastSendRef.current = { content, attachments };
    try {
      let conversationId = activeId;
      if (!conversationId) {
        const created = await apiRef.current.createAssistantConversation();
        conversationId = created.id;
        setActiveId(created.id);
      }
      await apiRef.current.sendAssistantMessage(conversationId, { content, attachments });
      const [list, detail] = await Promise.all([
        apiRef.current.listAssistantConversations(),
        apiRef.current.getAssistantConversation(conversationId),
      ]);
      setConversations(list);
      setMessages(detail.messages);
      setProposals(detail.proposals);
    } catch (error) {
      onErrorRef.current(error);
    } finally {
      setSending(false);
    }
  }, [activeId]);

  const retry = useCallback(async () => {
    if (lastSendRef.current) {
      await send(lastSendRef.current.content, lastSendRef.current.attachments);
    }
  }, [send]);

  const resolveProposal = useCallback(async (
    id: string,
    action: 'accept' | 'reject',
  ): Promise<ResolveProposalResult | undefined> => {
    try {
      const result: ResolveProposalResult = action === 'accept'
        ? await apiRef.current.acceptAssistantProposal(id)
        : { proposal: await apiRef.current.rejectAssistantProposal(id), task: null };
      setProposals(prev => prev.map(p => (p.id === id ? result.proposal : p)));
      return result;
    } catch (error) {
      onErrorRef.current(error);
      return undefined;
    }
  }, []);

  const saveSettings = useCallback(async (patch: AssistantSettingsPatch) => {
    try {
      setSettingsView(await apiRef.current.updateAssistantSettings(patch));
      return true;
    } catch (error) {
      onErrorRef.current(error);
      return false;
    }
  }, []);

  return {
    conversations, activeId, messages, proposals, settingsView, sending,
    selectConversation, startNewConversation, deleteConversation,
    send, retry, resolveProposal, saveSettings,
  };
}
