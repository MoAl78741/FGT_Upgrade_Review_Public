import { useCallback, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Upload, X, Play, Loader2, AlertTriangle } from "lucide-react";
import PdfDownloadHelper from "./PdfDownloadHelper";
import { api } from "../api";
import { pdfVersion as extractVersionFromName, validatePdfSelection } from "../utils/pdfSelection";

export default function PdfUploadForm() {
  const [files, setFiles]     = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [error, setError]     = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();
  const {data: limits} = useQuery({queryKey: ["capabilities"], queryFn: api.capabilities});

  const mutation = useMutation({
    mutationFn: () => api.uploadPdfs(files),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["jobs"] });
      setError("");
      setFiles([]);
    },
    onError: (e: Error) => setError(e.message),
  });

  function addFiles(incoming: FileList | File[]) {
    if (mutation.isPending) return;
    setError("");
    const selected = Array.from(incoming); // FileList is live; snapshot before resetting the input.
    setFiles(prev => [...prev, ...selected]);
  }

  function removeFile(index: number) {
    setFiles((prev) => prev.filter((_, i) => i !== index));
  }

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    addFiles(e.dataTransfer.files);
  }, [mutation.isPending]);

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (files.length === 0) { setError("Please select at least one PDF."); return; }
    if (!limits) { setError("Waiting for deployment limits. Try again shortly."); return; }
    const invalid = validatePdfSelection(files, limits);
    if (invalid) { setError(invalid); return; }
    mutation.mutate();
  }

  const selectionError = files.length && limits ? validatePdfSelection(files, limits) : undefined;
  const valid = !!limits && files.length > 0 && !selectionError;

  // Auto-fill to_version from filenames if not set
  const detectedVersions = files
    .map((f) => extractVersionFromName(f.name))
    .filter(Boolean) as string[];

  return (
    <form onSubmit={handleSubmit} className="bg-navy-800 border border-navy-700 rounded-xl overflow-hidden">
      {/* Top accent bar */}
      <div
        className="h-0.5"
        style={{ background: "linear-gradient(90deg, rgb(var(--accent)) 0%, rgb(var(--accent) / 0.3) 60%, transparent 100%)" }}
      />

      <div className="p-6">
        {/* Header */}
        <div className="flex items-center gap-2 mb-5">
          <div className="w-1 h-5 rounded-full" style={{ background: "rgb(var(--accent))" }} />
          <h2 className="text-white font-semibold text-sm tracking-wide uppercase">Upload Release Note PDFs</h2>
        </div>

        <PdfDownloadHelper files={files} maxFiles={limits?.max_files} />

        {/* Drop zone */}
        <div
          onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          role="button"
          tabIndex={mutation.isPending ? -1 : 0}
          aria-label="Choose release note PDFs"
          onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileInputRef.current?.click(); } }}
          onClick={() => fileInputRef.current?.click()}
          className={`mb-4 flex flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed cursor-pointer py-8 transition-all duration-150 ${
            dragging
              ? "border-brand-500 bg-brand-500/10"
              : "border-navy-600 hover:border-brand-500/60 bg-navy-900/40 hover:bg-navy-900/60"
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            disabled={mutation.isPending}
            multiple
            accept=".pdf"
            className="hidden"
            onChange={(e) => { if (e.target.files) addFiles(e.target.files); e.target.value = ""; }}
          />
          <Upload className={`w-6 h-6 transition-colors ${dragging ? "text-brand-500" : "text-gray-600"}`} />
          <p className="text-sm text-gray-400">
            Drop PDF(s) here or <span className="text-brand-500 font-medium">browse</span>
          </p>
          <p className="text-xs text-gray-600">Version is detected from the filename (e.g. fortios-v7.4.11-release-notes.pdf)</p>
        </div>

        {limits && <p className="text-xs text-gray-400 mb-4">Up to {limits.max_files} PDFs · {Math.round(limits.max_file_bytes / 1024**2)} MiB each · {Math.round(limits.max_total_bytes / 1024**2)} MiB total. Selected: {files.length} files, {(files.reduce((n, f) => n + f.size, 0) / 1024**2).toFixed(1)} MiB.</p>}
        {/* File list */}
        {files.length > 0 && (
          <div className="mb-4 space-y-1.5">
            {files.map((f, index) => {
              const detected = extractVersionFromName(f.name);
              return (
                <div
                  key={`${index}:${f.name}`}
                  className="flex items-center gap-2.5 px-3 py-2 bg-navy-900 border border-navy-700 rounded-lg"
                >
                  <FileText className="w-4 h-4 text-brand-500 shrink-0" />
                  <span className="text-sm text-gray-300 truncate flex-1 font-mono">{f.name}</span>
                  {detected && (
                    <span
                      className="text-xs font-mono px-1.5 py-0.5 rounded shrink-0"
                      style={{
                        background: "rgb(var(--accent) / 0.12)",
                        color: "rgb(var(--accent))",
                        border: "1px solid rgb(var(--accent) / 0.25)",
                      }}
                    >
                      v{detected}
                    </span>
                  )}
                  <button
                    type="button"
                    onClick={() => removeFile(index)}
                    disabled={mutation.isPending}
                    aria-label={`Remove ${f.name}`}
                    className="text-gray-600 hover:text-red-400 transition-colors shrink-0"
                  >
                    <X className="w-3.5 h-3.5" />
                  </button>
                </div>
              );
            })}
          </div>
        )}

        {/* Detected versions hint */}
        {detectedVersions.length > 0 && (
          <p className="text-xs text-gray-600 mb-4">
            Detected versions from filenames:{" "}
            <span className="text-gray-400 font-mono">{detectedVersions.join(", ")}</span>
          </p>
        )}

        {(error || selectionError) && (
          <div role="alert" className="text-red-400 text-sm mb-4 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2.5 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5" />
            <span>{error || selectionError}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={!valid || mutation.isPending}
          className="flex items-center gap-2 px-5 py-2.5 bg-brand-500 hover:bg-brand-600 disabled:opacity-40 disabled:cursor-not-allowed text-white font-semibold text-sm rounded-lg transition-all duration-150"
          style={{ boxShadow: valid && !mutation.isPending ? "0 2px 12px rgb(var(--accent) / 0.3)" : undefined }}
        >
          {mutation.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          {mutation.isPending ? "Uploading PDFs…" : "Process PDFs"}
        </button>
      </div>
    </form>
  );
}
