export interface Segment {
  start: number;
  end: number;
  polished_text?: string;
  text?: string;
}

export interface InterviewSummary {
  id: number;
  filename: string;
  status: 'processing' | 'completed' | 'completed_raw_only' | 'failed' | string;
  summary?: string | null;
  key_topics?: string[] | null;
  created_at?: string | null;
}

export interface InterviewDetail {
  id: number;
  filename: string;
  file_path?: string | null;
  status: 'processing' | 'completed' | 'completed_raw_only' | 'failed' | string;
  summary?: string | null;
  key_topics?: string[] | null;
  raw_transcript?: string | null;
  raw_segments?: Segment[] | null;
  polished_transcript?: string | null;
  polished_segments?: Segment[] | null;
  created_at?: string | null;
}

export interface SourceSegment {
  interview_id: number;
  filename: string;
  start: number;
  end: number;
  text: string;
}

export interface ChatRequest {
  question: string;
  interview_id?: number | null;
  limit?: number;
}

export interface ChatResponse {
  answer: string;
  sources: SourceSegment[];
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: string;
  sources?: SourceSegment[];
  isThinking?: boolean;
}

export interface UploadResponse {
  message: string;
  interview_id: number;
  status: string;
  summary?: string | null;
  key_topics?: string[] | null;
  raw_preview?: string | null;
  polished_preview?: string | null;
}
