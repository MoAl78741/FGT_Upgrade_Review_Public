export interface PdfLimits { max_files: number; max_file_bytes: number; max_total_bytes: number }
export interface PdfCandidate { name: string; size: number }
export function pdfVersion(name: string): string | null {
  return name.match(/(?<!\d)(\d{1,2}\.\d{1,2}\.\d{1,3})(?!\d)/)?.[1] ?? null;
}
export function validatePdfSelection(files: PdfCandidate[], limits: PdfLimits): string | undefined {
  const mib = (bytes: number) => `${Math.round(bytes / 1024**2)} MiB`;
  if (!files.length) return 'Select at least one PDF.';
  if (files.length > limits.max_files) return `Choose at most ${limits.max_files} PDFs per job.`;
  const versions = new Set<string>();
  for (const file of files) {
    if (!file.name.toLowerCase().endsWith('.pdf')) return `${file.name}: only PDF files are accepted.`;
    if (!file.size) return `${file.name}: this file is empty.`;
    if (file.size > limits.max_file_bytes) return `${file.name}: exceeds the ${mib(limits.max_file_bytes)} file limit.`;
    const version = pdfVersion(file.name);
    if (!version) return `${file.name}: include its FortiOS version in the filename, such as v7.4.11.pdf.`;
    if (versions.has(version)) return `Choose one PDF for version ${version}; compare revisions in separate jobs.`;
    versions.add(version);
  }
  if (files.reduce((n, f) => n + f.size, 0) > limits.max_total_bytes) return `Selected PDFs exceed the ${mib(limits.max_total_bytes)} total limit.`;
}
