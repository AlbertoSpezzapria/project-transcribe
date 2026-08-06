
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface InterviewSummary {
  id: number;
  filename: string;
  status: string;
  summary?: string;
  key_topics?: string[];
  created_at?: string;
}

export interface InterviewDetail extends InterviewSummary {
  file_path?: string;
  raw_transcript?: string;
  raw_segments?: Array<{ start: number; end: number; text: string }>;
  polished_transcript?: string;
  polished_segments?: Array<{ start: number; end: number; polished_text: string }>;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  sources?: Array<{
    interview_id: number;
    filename: string;
    start: number;
    end: number;
    text: string;
  }>;
}

// 1. Upload dell'audio
export async function uploadAudio(file: File) {
  const formData = new FormData();
  formData.append("file", file);

  const res = await fetch(`${API_BASE_URL}/upload`, {
    method: "POST",
    body: formData,
  });

  if (!res.ok) throw new Error("Errore durante il caricamento");
  return res.json();
}

// 2. Fetch di tutte le interviste
export async function getInterviews(): Promise<InterviewSummary[]> {
  const res = await fetch(`${API_BASE_URL}/interviews`, { cache: 'no-store' });
  if (!res.ok) throw new Error("Errore durante il recupero delle interviste");
  return res.json();
}

// 3. Fetch del dettaglio di una singola intervista
export async function getInterviewById(id: number): Promise<InterviewDetail> {
  const res = await fetch(`${API_BASE_URL}/interviews/${id}`, { cache: 'no-store' });
  if (!res.ok) throw new Error("Intervista non trovata");
  return res.json();
}

// 4. Invio messaggio alla Chat RAG (Globale o Contestuale)
export async function sendChatMessage(question: string, interviewId?: number) {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      interview_id: interviewId || null,
      limit: 5,
    }),
  });

  if (!res.ok) throw new Error("Errore durante la generazione della risposta RAG");
  return res.json();
}