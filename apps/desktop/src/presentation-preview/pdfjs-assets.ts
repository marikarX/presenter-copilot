import pdfjsModuleUrl from "pdfjs-dist/build/pdf.min.mjs?url";
import pdfjsWorkerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

export const PREVIEW_PDFJS = {
  moduleUrl: new URL(pdfjsModuleUrl, import.meta.url).href,
  workerUrl: new URL(pdfjsWorkerUrl, import.meta.url).href,
} as const;
