"use client";

import { useEditor, EditorContent } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import { Bold, Italic, Heading2, List, ListOrdered } from 'lucide-react'
import { useEffect } from 'react';

interface TipTapEditorProps {
  content: string;
  onChange: (html: string) => void;
}

export default function TipTapEditor({ content, onChange }: TipTapEditorProps) {
  const editor = useEditor({
    extensions: [StarterKit],
    content: content,
    editorProps: {
      attributes: {
        class: 'prose prose-invert prose-sm sm:prose-base max-w-none focus:outline-none min-h-[300px] p-6',
      },
    },
    onUpdate: ({ editor }) => {
      onChange(editor.getHTML());
    },
  })

  // Aggiorna l'editor se il contenuto esterno cambia (es. quando l'AI genera la bozza)
  useEffect(() => {
    if (editor && content !== editor.getHTML()) {
      editor.commands.setContent(content, false);
    }
  }, [content, editor]);

  if (!editor) return null;

  return (
    <div className="flex flex-col h-full bg-slate-900 rounded-xl border border-slate-800 shadow-lg overflow-hidden">
      {/* TOOLBAR */}
      <div className="flex items-center gap-2 bg-slate-800/80 p-3 border-b border-slate-700">
        <button
          onClick={() => editor.chain().focus().toggleBold().run()}
          className={`p-2 rounded-md transition-colors ${editor.isActive('bold') ? 'bg-indigo-600 text-white' : 'hover:bg-slate-700 text-slate-300'}`}
        >
          <Bold className="w-4 h-4" />
        </button>
        <button
          onClick={() => editor.chain().focus().toggleItalic().run()}
          className={`p-2 rounded-md transition-colors ${editor.isActive('italic') ? 'bg-indigo-600 text-white' : 'hover:bg-slate-700 text-slate-300'}`}
        >
          <Italic className="w-4 h-4" />
        </button>
        <div className="w-px h-5 bg-slate-700 mx-2" />
        <button
          onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
          className={`p-2 rounded-md transition-colors ${editor.isActive('heading', { level: 2 }) ? 'bg-indigo-600 text-white' : 'hover:bg-slate-700 text-slate-300'}`}
        >
          <Heading2 className="w-4 h-4" />
        </button>
        <div className="w-px h-5 bg-slate-700 mx-2" />
        <button
          onClick={() => editor.chain().focus().toggleBulletList().run()}
          className={`p-2 rounded-md transition-colors ${editor.isActive('bulletList') ? 'bg-indigo-600 text-white' : 'hover:bg-slate-700 text-slate-300'}`}
        >
          <List className="w-4 h-4" />
        </button>
        <button
          onClick={() => editor.chain().focus().toggleOrderedList().run()}
          className={`p-2 rounded-md transition-colors ${editor.isActive('orderedList') ? 'bg-indigo-600 text-white' : 'hover:bg-slate-700 text-slate-300'}`}
        >
          <ListOrdered className="w-4 h-4" />
        </button>
      </div>

      {/* AREA DI TESTO */}
      <div className="flex-1 overflow-y-auto bg-transparent">
        <EditorContent editor={editor} />
      </div>
    </div>
  )
}