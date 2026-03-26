import { useState, useRef, useEffect, KeyboardEvent } from "react";
import {
  Bot,
  Send,
  ChevronRight,
  Sparkles,
  RefreshCw,
  FileCheck,
  Users,
  ListFilter,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { invokeRailAgent } from "../../lib/agent-gateway";
import { useAuthStore } from "../../store/authStore";
import { useALISRole } from "../../hooks/useALISRole";

interface Message {
  id: string;
  role: "ai" | "user";
  content: string;
  timestamp: Date;
  actionCards?: ActionCard[];
}

interface ActionCard {
  label: string;
  description: string;
  intent: string;
  variant: "approve" | "review" | "generate" | "default";
}

const QUICK_ACTIONS = [
  { label: "Review queue", icon: ListFilter, intent: "show review queue" },
  { label: "Pending docs", icon: FileCheck, intent: "show pending documents" },
  { label: "Gen merit list", icon: Sparkles, intent: "generate merit list" },
  { label: "Eligible batch", icon: Users, intent: "run batch eligibility check" },
];

const INITIAL_MESSAGES: Message[] = [];

function formatTime(date: Date): string {
  return date.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-3 mb-5">
      <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0"
        style={{ background: "rgba(167,139,250,0.15)", border: "1px solid rgba(167,139,250,0.25)" }}>
        <Bot className="w-3.5 h-3.5" style={{ color: "#a78bfa" }} />
      </div>
      <div className="chat-bubble-ai px-4 py-3 flex items-center gap-1.5">
        {[0, 150, 300].map((delay) => (
          <span key={delay} className="w-1.5 h-1.5 rounded-full"
            style={{
              background: "rgba(167,139,250,0.6)",
              animation: `pulse-live 1.2s ease ${delay}ms infinite`,
            }} />
        ))}
      </div>
    </div>
  );
}

function ActionCardRow({ cards }: { cards: ActionCard[] }) {
  return (
    <div className="flex flex-wrap gap-2 mt-3">
      {cards.map((card) => (
        <button
          key={card.intent}
          className="flex items-center gap-2 px-3 py-2 rounded-lg text-left transition-all"
          style={{
            background: card.variant === "approve"
              ? "rgba(52,211,153,0.08)"
              : card.variant === "review"
              ? "rgba(251,191,36,0.08)"
              : card.variant === "generate"
              ? "rgba(129,140,248,0.08)"
              : "rgba(255,255,255,0.04)",
            border: `1px solid ${
              card.variant === "approve" ? "rgba(52,211,153,0.2)"
              : card.variant === "review" ? "rgba(251,191,36,0.2)"
              : card.variant === "generate" ? "rgba(129,140,248,0.2)"
              : "rgba(255,255,255,0.08)"
            }`,
          }}
          onClick={() => {}}
        >
          <div>
            <div className="text-[11px] font-semibold" style={{
              color: card.variant === "approve" ? "#34d399"
                : card.variant === "review" ? "#fbbf24"
                : card.variant === "generate" ? "#818cf8"
                : "#94a3b8",
            }}>
              {card.label}
            </div>
            {card.description && (
              <div className="text-[10px] mt-0.5" style={{ color: "#64748b" }}>{card.description}</div>
            )}
          </div>
          <ChevronRight className="w-3 h-3 ml-auto flex-shrink-0" style={{ color: "#475569" }} />
        </button>
      ))}
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isAI = message.role === "ai";

  if (isAI) {
    return (
      <div className="flex items-start gap-3 mb-5 fade-up-1">
        {/* AI avatar */}
        <div className="w-7 h-7 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ background: "rgba(167,139,250,0.15)", border: "1px solid rgba(167,139,250,0.25)" }}>
          <Bot className="w-3.5 h-3.5" style={{ color: "#a78bfa" }} />
        </div>

        <div className="flex-1 min-w-0">
          <div className="chat-bubble-ai px-4 py-3 inline-block max-w-full">
            <p className="text-[13px] leading-relaxed whitespace-pre-line" style={{ color: "#cbd5e1" }}>
              {message.content}
            </p>
            {message.actionCards && <ActionCardRow cards={message.actionCards} />}
          </div>
          <div className="text-[10px] mt-1.5 ml-1" style={{ color: "#475569" }}>
            {formatTime(message.timestamp)}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-start justify-end gap-3 mb-5 fade-up-1">
      <div className="flex-1 min-w-0 flex flex-col items-end">
        <div className="chat-bubble-user px-4 py-3 inline-block max-w-[85%]">
          <p className="text-[13px] leading-relaxed" style={{ color: "#e2e8f0" }}>
            {message.content}
          </p>
        </div>
        <div className="text-[10px] mt-1.5 mr-1" style={{ color: "#475569" }}>
          {formatTime(message.timestamp)}
        </div>
      </div>
    </div>
  );
}

interface ChatPanelProps {
  isOpen: boolean;
  onToggle: () => void;
  moduleContext?: string;
}

export default function ChatPanel({ isOpen, onToggle, moduleContext = "admissions" }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>(INITIAL_MESSAGES);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const [agentContext, setAgentContext] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { user } = useAuthStore();
  const { role } = useALISRole();

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || !user) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: text,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    const recentMessages = messages.slice(-5).map((m) => ({
      role: m.role === "ai" ? "agent" : "user",
      text: m.content,
    }));

    const resp = await invokeRailAgent({
      actorId: user.id,
      orgId: user.tenant_id,
      role,
      view: moduleContext,
      message: text,
      agentContext,
      recentMessages,
    });

    setIsTyping(false);

    if (resp.agentContext !== undefined) {
      setAgentContext(resp.agentContext ?? null);
    }

    if (resp.message) {
      const aiMsg: Message = {
        id: (Date.now() + 1).toString(),
        role: "ai",
        content: resp.message,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, aiMsg]);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleQuickAction = (intent: string) => {
    setInput(intent);
    textareaRef.current?.focus();
  };

  // Collapsed state — just a thin icon bar
  if (!isOpen) {
    return (
      <div
        className="flex flex-col items-center py-4 gap-3 flex-shrink-0"
        style={{
          width: 52,
          background: "rgba(255,255,255,0.02)",
          borderLeft: "1px solid rgba(255,255,255,0.06)",
        }}
      >
        <button
          onClick={onToggle}
          className="w-9 h-9 rounded-xl flex items-center justify-center transition-all"
          style={{
            background: "rgba(167,139,250,0.1)",
            border: "1px solid rgba(167,139,250,0.2)",
          }}
          title="Open ALIS Assistant"
        >
          <Bot className="w-4 h-4" style={{ color: "#a78bfa" }} />
        </button>
        <div
          className="writing-mode-vertical text-[9px] font-semibold tracking-[0.15em] uppercase"
          style={{ color: "#475569", writingMode: "vertical-rl" }}
        >
          ALIS
        </div>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col flex-shrink-0"
      style={{
        width: 380,
        background: "rgba(255,255,255,0.015)",
        borderLeft: "1px solid rgba(255,255,255,0.07)",
      }}
    >
      {/* Panel header */}
      <div className="flex items-center justify-between px-5 py-4 flex-shrink-0"
        style={{ borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl flex items-center justify-center"
            style={{
              background: "rgba(167,139,250,0.12)",
              border: "1px solid rgba(167,139,250,0.22)",
              boxShadow: "0 0 16px rgba(167,139,250,0.1)",
            }}>
            <Sparkles className="w-4 h-4" style={{ color: "#a78bfa" }} />
          </div>
          <div>
            <div className="text-[13px] font-semibold" style={{ color: "#e2e8f0" }}>
              ALIS Assistant
            </div>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="status-dot-live" />
              <span className="text-[10px]" style={{ color: "#64748b" }}>
                qwen2.5 · local · {moduleContext}
              </span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <button
            className="btn-ghost w-8 h-8 p-0 flex items-center justify-center"
            onClick={() => { setMessages([]); setAgentContext(null); }}
            title="Clear chat"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            className="btn-ghost w-8 h-8 p-0 flex items-center justify-center"
            onClick={onToggle}
            title="Collapse"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 pt-5 pb-2 min-h-0">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} message={msg} />
        ))}
        {isTyping && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>

      {/* Quick actions */}
      <div className="px-4 pb-2">
        <div className="flex flex-wrap gap-1.5">
          {QUICK_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <button
                key={action.intent}
                onClick={() => handleQuickAction(action.intent)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-[10px] font-medium transition-all"
                style={{
                  background: "rgba(255,255,255,0.03)",
                  border: "1px solid rgba(255,255,255,0.07)",
                  color: "#64748b",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = "rgba(129,140,248,0.08)";
                  e.currentTarget.style.color = "#818cf8";
                  e.currentTarget.style.borderColor = "rgba(129,140,248,0.18)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = "rgba(255,255,255,0.03)";
                  e.currentTarget.style.color = "#64748b";
                  e.currentTarget.style.borderColor = "rgba(255,255,255,0.07)";
                }}
              >
                <Icon className="w-3 h-3" />
                {action.label}
              </button>
            );
          })}
        </div>
      </div>

      {/* Input */}
      <div className="px-4 pb-4 pt-2 flex-shrink-0">
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="What do you need to do?"
            rows={2}
            className={cn("chat-input pr-12")}
            style={{ minHeight: 64, maxHeight: 120 }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || isTyping}
            className="absolute right-3 bottom-3 w-8 h-8 rounded-lg flex items-center justify-center transition-all"
            style={{
              background: input.trim() && !isTyping
                ? "rgba(129,140,248,0.2)"
                : "rgba(255,255,255,0.04)",
              border: `1px solid ${input.trim() && !isTyping ? "rgba(129,140,248,0.3)" : "rgba(255,255,255,0.08)"}`,
              color: input.trim() && !isTyping ? "#818cf8" : "#475569",
              cursor: input.trim() && !isTyping ? "pointer" : "not-allowed",
            }}
          >
            {isTyping
              ? <RefreshCw className="w-3.5 h-3.5 spin-slow" />
              : <Send className="w-3.5 h-3.5" />
            }
          </button>
        </div>
        <div className="text-[10px] mt-1.5 text-center" style={{ color: "#334155" }}>
          ↵ send · shift+↵ new line
        </div>
      </div>
    </div>
  );
}

