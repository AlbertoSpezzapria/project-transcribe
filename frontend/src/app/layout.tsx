import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Interview AI Platform",
  description: "Trascrizione e analisi RAG delle interviste",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="it">
      <body className="bg-slate-900 text-slate-100 min-h-screen">
        {children}
      </body>
    </html>
  );
}