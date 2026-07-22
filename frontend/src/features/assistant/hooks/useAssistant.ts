import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ApiError,
  type AssistantAttachment,
  type AssistantConversationSummary,
  type AssistantMessage,
  type AssistantProposalBatch,
  type AssistantSettingsPatch,
  type AssistantSettingsView,
  type ConfirmProposalItemInput,
  type ProposalBatchResolveResult,
  type TodoApi,
} from '@/shared/api/contracts';

export interface AssistantState {
  conversations: AssistantConversationSummary[];
  activeId: string | null;
  messages: AssistantMessage[];
  proposalBatches: AssistantProposalBatch[];
  settingsView: AssistantSettingsView | null;
  sending: boolean;
  submittingBatchIds: ReadonlySet<string>;
  selectConversation: (id: string) => Promise<void>;
  startNewConversation: () => void;
  deleteConversation: (id: string) => Promise<void>;
  send: (content: string, attachments: AssistantAttachment[]) => Promise<void>;
  retry: (turnId: string) => Promise<void>;
  confirmBatch: (
    id: string,
    items: ConfirmProposalItemInput[],
  ) => Promise<ProposalBatchResolveResult | undefined>;
  rejectBatch: (id: string) => Promise<ProposalBatchResolveResult | undefined>;
  saveSettings: (patch: AssistantSettingsPatch) => Promise<boolean>;
}

export function useAssistant(
  api: TodoApi,
  onError: (error: unknown) => void,
): AssistantState {
  const [conversations, setConversations] = useState<AssistantConversationSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [proposalBatches, setProposalBatches] = useState<AssistantProposalBatch[]>([]);
  const [settingsView, setSettingsView] = useState<AssistantSettingsView | null>(null);
  const [sending, setSending] = useState(false);
  const [submittingBatchIds, setSubmittingBatchIds] = useState<ReadonlySet<string>>(
    () => new Set<string>(),
  );
  const messagesRef = useRef(messages);
  const submittingRef = useRef(new Set<string>());
  const apiRef = useRef(api);
  const onErrorRef = useRef(onError);
  messagesRef.current = messages;
  apiRef.current = api;
  onErrorRef.current = onError;

  const selectConversation = useCallback(async (id: string) => {
    try {
      const detail = await apiRef.current.getAssistantConversation(id);
      setActiveId(id);
      setMessages(detail.messages);
      setProposalBatches(detail.proposalBatches);
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
    setProposalBatches([]);
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

  const dispatchMessage = useCallback(async (
    conversationId: string,
    turnId: string,
    content: string,
    attachments: AssistantAttachment[],
  ) => {
    setSending(true);
    let sendFailed = false;
    let sendError: unknown;
    try {
      await apiRef.current.sendAssistantMessage(conversationId, {
        turnId,
        content,
        attachments,
      });
    } catch (error) {
      sendFailed = true;
      sendError = error;
    }

    const [listResult, detailResult] = await Promise.allSettled([
      apiRef.current.listAssistantConversations(),
      apiRef.current.getAssistantConversation(conversationId),
    ]);
    if (listResult.status === 'fulfilled') {
      setConversations(listResult.value);
    }
    if (detailResult.status === 'fulfilled') {
      setMessages(detailResult.value.messages);
      setProposalBatches(detailResult.value.proposalBatches);
    }

    if (sendFailed) {
      onErrorRef.current(sendError);
    } else if (detailResult.status === 'rejected') {
      onErrorRef.current(detailResult.reason);
    } else if (listResult.status === 'rejected') {
      onErrorRef.current(listResult.reason);
    }
    setSending(false);
  }, []);

  const send = useCallback(async (
    content: string,
    attachments: AssistantAttachment[],
  ) => {
    let conversationId = activeId;
    if (!conversationId) {
      setSending(true);
      try {
        const created = await apiRef.current.createAssistantConversation();
        conversationId = created.id;
        setActiveId(created.id);
      } catch (error) {
        onErrorRef.current(error);
        setSending(false);
        return;
      }
    }
    await dispatchMessage(
      conversationId,
      crypto.randomUUID(),
      content,
      attachments,
    );
  }, [activeId, dispatchMessage]);

  const retry = useCallback(async (turnId: string) => {
    const userMessage = messagesRef.current.find(message => (
      message.role === 'user' && message.turnId === turnId
    ));
    if (!userMessage || !activeId) {
      onErrorRef.current(new ApiError(
        'business', 'ASSISTANT_TURN_NOT_FOUND', 'Assistant turn not found', 404,
      ));
      return;
    }
    await dispatchMessage(
      activeId,
      turnId,
      userMessage.content,
      userMessage.attachments,
    );
  }, [activeId, dispatchMessage]);

  const runBatchMutation = useCallback(async (
    id: string,
    operation: () => Promise<ProposalBatchResolveResult>,
  ): Promise<ProposalBatchResolveResult | undefined> => {
    if (submittingRef.current.has(id)) return undefined;
    submittingRef.current.add(id);
    setSubmittingBatchIds(new Set(submittingRef.current));
    try {
      const result = await operation();
      setProposalBatches(current => current.map(currentBatch => (
        currentBatch.id === id ? result.batch : currentBatch
      )));
      return result;
    } catch (error) {
      onErrorRef.current(error);
      return undefined;
    } finally {
      submittingRef.current.delete(id);
      setSubmittingBatchIds(new Set(submittingRef.current));
    }
  }, []);

  const confirmBatch = useCallback((
    id: string,
    items: ConfirmProposalItemInput[],
  ) => runBatchMutation(
    id,
    () => apiRef.current.confirmAssistantProposalBatch(id, { items }),
  ), [runBatchMutation]);

  const rejectBatch = useCallback((id: string) => runBatchMutation(
    id,
    () => apiRef.current.rejectAssistantProposalBatch(id),
  ), [runBatchMutation]);

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
    conversations,
    activeId,
    messages,
    proposalBatches,
    settingsView,
    sending,
    submittingBatchIds,
    selectConversation,
    startNewConversation,
    deleteConversation,
    send,
    retry,
    confirmBatch,
    rejectBatch,
    saveSettings,
  };
}
