"use client";

import { useState, useEffect } from "react";
import { PenTool, FileText, Send, Loader2, Save } from "lucide-react";
import TipTapEditor from "@/components/TipTapEditor"; 

export default function WorkspacePage() {
  const [interviews, setInterviews] = useState<any[]>([]);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [formatType, setFormatType] = useState("article");
  const [customPrompt, setCustomPrompt] = useState("");
  
  // Stati per la gestione della bozza
  const [draftTitle, setDraftTitle] = useState("Nuova Bozza");
  const [draftContent, setDraftContent] = useState("");
  
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    fetch("http://localhost:8000/interviews")
      .then((res) => res.json())
      .then((data) => setInterviews(data))
      .catch((err) => console.error(err));
  }, []);

  const handleGenerate = async () => {
    if (selectedIds.length === 0) return alert("Seleziona almeno un'intervista");
    
    setIsGenerating(true);
    try {
      const res = await fetch("http://localhost:8000/draft/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          interview_ids: selectedIds,
          format_type: formatType,
          additional_instructions: customPrompt
        }),
      });
      const data = await res.json();
      
      // Convertiamo il markdown dell'AI in semplice HTML di base per TipTap (puoi migliorarlo con librerie come 'marked' in futuro)
      const htmlContent = data.draft.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>');
      setDraftContent(`<p>${htmlContent}</p>`);
    } catch (err) {
      console.error(err);
      alert("Errore durante la generazione");
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSave = async () => {
    if (!draftContent || draftContent === "<p></p>") return alert("La bozza è vuota!");
    
    setIsSaving(true);
    try {
      const res = await fetch("http://localhost:8000/drafts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title: draftTitle,
          content: draftContent,
          format_type: formatType
        }),
      });
      
      if (res.ok) {
        alert("Bozza salvata con successo!");
      } else {
        alert("Errore nel salvataggio");
      }
    } catch (err) {
      console.error(err);
      alert("Errore di connessione al server");
    } finally {
      setIsSaving(false);
    }
  };

  const toggleSelection = (id: number) => {
    setSelectedIds((prev) => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    );
  };

  return (
    <div className="flex h-[calc(100vh-64px)] overflow-hidden bg-slate-950 text-slate-200 p-4 gap-4">
      
      {/* PANNELLO SINISTRO: Controlli e Fonti */}
      <div className="w-1/3 flex flex-col gap-6 bg-slate-900 p-6 rounded-xl border border-slate-800 overflow-y-auto shadow-lg">
        {/* ... (Codice esistente per selezione fonti, formato e custom prompt) ... */}
        
        {/* Riporto qui i controlli per chiarezza */}
        <div>
          <h2 className="text-xl font-bold flex items-center gap-2 mb-4">
            <FileText className="w-5 h-5 text-indigo-400" />
            1. Seleziona Fonti
          </h2>
          <div className="space-y-2">
            {interviews.map((inv) => (
              <label key={inv.id} className="flex items-start gap-3 p-3 rounded-lg hover:bg-slate-800 border border-slate-700/50 cursor-pointer">
                <input type="checkbox" className="mt-1 accent-indigo-500 w-4 h-4" checked={selectedIds.includes(inv.id)} onChange={() => toggleSelection(inv.id)} />
                <span className="text-sm font-medium">{inv.filename}</span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <h2 className="text-xl font-bold flex items-center gap-2 mb-4">
            <PenTool className="w-5 h-5 text-indigo-400" />
            2. Genera Contenuto
          </h2>
          <select className="w-full bg-slate-950 border border-slate-700 rounded-lg p-3 text-sm mb-4" value={formatType} onChange={(e) => setFormatType(e.target.value)}>
            <option value="article">📰 Articolo Giornalistico</option>
            <option value="linkedin">💼 Post LinkedIn</option>
            <option value="newsletter">✉️ Newsletter Brief</option>
            <option value="qa">💬 Intervista Botta & Risposta</option>
          </select>
          <button 
            onClick={handleGenerate}
            disabled={isGenerating || selectedIds.length === 0}
            className="w-full flex items-center justify-center gap-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-700 text-white font-semibold py-3 px-4 rounded-lg"
          >
            {isGenerating ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            {isGenerating ? "Generazione..." : "Genera Bozza con AI"}
          </button>
        </div>
      </div>

      {/* PANNELLO DESTRO: Editor TipTap e Salvataggio */}
      <div className="w-2/3 flex flex-col gap-4">
        
        {/* Header Salvataggio */}
        <div className="flex items-center gap-4 bg-slate-900 p-4 rounded-xl border border-slate-800 shadow-lg">
          <input 
            type="text" 
            value={draftTitle}
            onChange={(e) => setDraftTitle(e.target.value)}
            className="flex-1 bg-slate-950 border border-slate-700 text-slate-100 rounded-lg p-2 font-medium focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            placeholder="Titolo della bozza..."
          />
          <button 
            onClick={handleSave}
            disabled={isSaving}
            className="flex items-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 text-white font-semibold py-2 px-6 rounded-lg transition-colors"
          >
            {isSaving ? <Loader2 className="w-5 h-5 animate-spin" /> : <Save className="w-5 h-5" />}
            {isSaving ? "Salvataggio..." : "Salva Documento"}
          </button>
        </div>

        {/* TipTap Editor */}
        <div className="flex-1 overflow-hidden">
          <TipTapEditor 
            content={draftContent} 
            onChange={(html) => setDraftContent(html)} 
          />
        </div>

      </div>

    </div>
  );
}