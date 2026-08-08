"use client";

import { useState, useRef, useEffect, KeyboardEvent } from "react";
import { Send, Bot, User, Sparkles, Clock, Trash2, ArrowUpRight, HelpCircle } from "lucide-react";
import { ChatMessage, SourceSegment, ChatResponse } from "@/types";
import { API_BASE_URL } from "@/lib/api";

interface ChatWindowProps {
  interviewId?: number;
  title?: string;
  subtitle?: string;
  onSourceClick?: (source: SourceSegment) => void;
}

export default function ChatWindow({
  interviewId,
  title = "Chat RAG AI",
  subtitle = "Fai domande ed estrai informazioni dai dati trascritti",
  onSourceClick,
}: ChatWindowProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "welcome",
      role: "assistant",
      content: interviewId
        ? "Ciao! Sono l'assistente RAG per questa intervista. Puoi chiedermi qualsiasi dettaglio, argomento trattato o estrarre citazioni con timestamp esatti."
        : "Benvenuto nella Chat RAG Globale sull'intero archivio delle tue interviste! Chiedimi pure un riassunto, dei confronti o informazioni specifiche.",
      timestamp: new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);

  const chatEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, loading]);

  const suggestedQuestions = interviewId
    ? [
        "Quali sono i punti principali trattati?",
        "Quali decisioni o conclusioni sono state prese?",
        "Sintetizza gli argomenti salienti in elenco puntato",
      ]
    : [
        "Sintetizza i temi trattati nelle ultime interviste",
        "Quali sono i problemi ricorrenti citati?",
        "Cosa è stato detto a proposito dei costi e dei tempi?",
      ];

  const handleSend = async (textToSend?: string) => {
    const queryText = (textToSend || input).trim();
    if (!queryText || loading) return;

    const userMessage: ChatMessage = {
      id: Date.now().toString(),
      role: "user",
      content: queryText,
      timestamp: new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMessage]);
    if (!textToSend) setInput("");
    setLoading(true);

    try {
      const res = await fetch(`${API_BASE_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          question: queryText,
          interview_id: interviewId || null,
          limit: 5,
        }),
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => null);
        throw new Error(errData?.detail || "Errore nella comunicazione col server RAG");
      }

      const data: ChatResponse = await res.json();

      const assistantMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: data.answer,
        sources: data.sources,
        timestamp: new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
      };

      setMessages((prev) => [...prev, assistantMessage]);
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        id: (Date.now() + 1).toString(),
        role: "assistant",
        content: `⚠️ Non è stato possibile elaborare la risposta: ${err.message}`,
        timestamp: new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatTimestamp = (seconds: number) => {
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m.toString().padStart(2, "0")}:${s.toString().padStart(2, "0")}`;
  };

  const clearChat = () => {
    setMessages([
      {
        id: "welcome-reset",
        role: "assistant",
        content: "Conversazione azzerata. Fai una nuova domanda!",
        timestamp: new Date().toLocaleTimeString("it-IT", { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  };

  return (
    <div className="flex flex-col h-full rounded-2xl bg-slate-900/80 border border-slate-800/80 shadow-2xl backdrop-blur-md overflow-hidden">
      {/* Header Chat */}
      <div className="px-5 py-4 bg-slate-950/60 border-b border-slate-800/80 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 text-white shadow-md shadow-indigo-500/20">
            <Bot className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <span>{title}</span>
              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                {interviewId ? `Intervista #${interviewId}` : "Archivio Globale"}
              </span>
            </h3>
            <p className="text-xs text-slate-400">{subtitle}</p>
          </div>
        </div>

        <button
          type="button"
          onClick={clearChat}
          className="p-2 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 transition-colors"
          title="Cancella conversazione"
        >
          <Trash2 className="w-4 h-4" />
        </button>
      </div>

      {/* Messaggi List */}
      <div className="flex-1 overflow-y-auto p-5 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 ${msg.role === "user" ? "justify-end" : "justify-start"}`}
          >
            {msg.role === "assistant" && (
              <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 flex items-center justify-center shrink-0 mt-1">
                <Sparkles className="w-4 h-4" />
              </div>
            )}

            <div className={`flex flex-col max-w-[85%] sm:max-w-[75%] ${msg.role === "user" ? "items-end" : "items-start"}`}>
              <div
                className={`p-4 rounded-2xl text-sm leading-relaxed ${
                  msg.role === "user"
                    ? "bg-gradient-to-r from-indigo-600 to-indigo-700 text-white shadow-md shadow-indigo-600/20 rounded-br-none"
                    : "bg-slate-950/70 border border-slate-800/80 text-slate-200 shadow-sm rounded-bl-none"
                }`}
              >
                <div className="whitespace-pre-wrap">{msg.content}</div>

                {/* Fonti e Citazioni per risposte Assistant */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-slate-800/80">
                    <p className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2 flex items-center gap-1">
                      <Clock className="w-3 h-3 text-indigo-400" />
                      <span>Fonti Estratte dal Vettoriale:</span>
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {msg.sources.map((src, i) => (
                        <div
                          key={i}
                          onClick={() => onSourceClick && onSourceClick(src)}
                          className={`group p-2 rounded-xl bg-slate-900/90 border border-slate-800 text-xs transition-all ${
                            onSourceClick ? "cursor-pointer hover:border-indigo-500/50 hover:bg-slate-800/80" : ""
                          }`}
                        >
                          <div className="flex items-center justify-between text-indigo-300 font-medium mb-1">
                            <span className="truncate max-w-[200px]">{src.filename}</span>
                            <span className="px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-400 font-mono text-[10px] flex items-center gap-1">
                              [{formatTimestamp(src.start)} - {formatTimestamp(src.end)}]
                              {onSourceClick && <ArrowUpRight className="w-3 h-3 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />}
                            </span>
                          </div>
                          <p className="text-slate-400 text-[11px] line-clamp-2 italic">&ldquo;{src.text}&rdquo;</p>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>

              <span className="text-[10px] text-slate-400 mt-1 px-1">{msg.timestamp}</span>
            </div>

            {msg.role === "user" && (
              <div className="w-8 h-8 rounded-xl bg-slate-800 border border-slate-700 text-slate-300 flex items-center justify-center shrink-0 mt-1">
                <User className="w-4 h-4" />
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex gap-3 justify-start">
            <div className="w-8 h-8 rounded-xl bg-indigo-600/20 border border-indigo-500/30 text-indigo-400 flex items-center justify-center shrink-0">
              <Sparkles className="w-4 h-4 animate-spin" />
            </div>
            <div className="p-4 rounded-2xl bg-slate-950/70 border border-slate-800 text-slate-400 text-xs flex items-center gap-2">
              <div className="flex gap-1">
                <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce" />
                <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce [animation-delay:0.2s]" />
                <span className="w-2 h-2 rounded-full bg-indigo-500 animate-bounce [animation-delay:0.4s]" />
              </div>
              <span>Ricerca semantica Qdrant e sintesi LLM in corso...</span>
            </div>
          </div>
        )}
        <div ref={chatEndRef} />
      </div>

      {/* Suggested Questions */}
      {messages.length <= 2 && !loading && (
        <div className="px-5 py-2 bg-slate-950/40 border-t border-slate-800/40">
          <p className="text-[11px] text-slate-400 font-medium mb-1.5 flex items-center gap-1">
            <HelpCircle className="w-3 h-3 text-indigo-400" /> Domande suggerite:
          </p>
          <div className="flex flex-wrap gap-1.5">
            {suggestedQuestions.map((q, idx) => (
              <button
                key={idx}
                type="button"
                onClick={() => handleSend(q)}
                className="text-xs px-2.5 py-1 rounded-lg bg-slate-800/80 hover:bg-indigo-600/20 hover:border-indigo-500/40 text-slate-300 hover:text-indigo-300 border border-slate-700/60 transition-all text-left"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Bar */}
      <div className="p-4 bg-slate-950/80 border-t border-slate-800/80">
        <div className="relative flex items-center">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={interviewId ? "Fai una domanda su questa intervista..." : "Fai una domanda sull'intero archivio..."}
            disabled={loading}
            className="w-full pl-4 pr-12 py-3 rounded-xl bg-slate-900 border border-slate-800 text-sm text-slate-100 placeholder-slate-400 focus:outline-none focus:border-indigo-500/80 focus:ring-1 focus:ring-indigo-500/80 transition-all"
          />
          <button
            type="button"
            onClick={() => handleSend()}
            disabled={!input.trim() || loading}
            className="absolute right-2 p-2 rounded-lg bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 transition-colors"
          >
            <Send className="w-4 h-4" />
          </button>
        </div>
      </div>
    </div>
  );
}
