import {useQuery} from "@tanstack/react-query";
import ProcessingSettings from "./ProcessingSettings";
import {api} from "../api";
import { useState, useEffect, useRef } from "react";
import { Settings, X, BookOpen } from "lucide-react";
import { useSettings } from "../contexts/SettingsContext";



export default function SettingsModal() {
  const {data: caps} = useQuery({queryKey: ["capabilities"], queryFn: api.capabilities});
  const [open, setOpen] = useState(false);
  const { settings, setSettings } = useSettings();
  const modalRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    function onClick(e: MouseEvent) {
      if (modalRef.current && !modalRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  return (
    <>
      {/* Gear button */}
      <div className="relative group">
        <button
          onClick={() => setOpen(true)}
          aria-label="Settings"
          className="flex items-center justify-center w-8 h-8 rounded-lg transition-all duration-150 hover:scale-105"
          style={{
            background: "rgb(var(--accent) / 0.1)",
            border: "1px solid rgb(var(--accent) / 0.2)",
          }}
        >
          <Settings className="w-4 h-4 text-brand-500" />
        </button>
        <span className="absolute top-full right-0 mt-2 px-2 py-1 text-xs bg-navy-900 text-white rounded whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none border border-navy-700">
          Settings
        </span>
      </div>

      {/* Backdrop + modal */}
      {open && (
        <div className="fixed inset-0 z-50 flex items-start justify-end p-4 pt-14">
          <div className="fixed inset-0 bg-black/50" aria-hidden />
          <div
            ref={modalRef}
            role="dialog" aria-modal="true" aria-label="Settings"
            className="relative bg-navy-800 border border-navy-700 rounded-xl shadow-2xl w-full max-w-lg max-h-[calc(100dvh-5rem)] overflow-y-auto"
          >
            {/* Accent bar */}
            <div
              className="h-0.5"
              style={{ background: "linear-gradient(90deg, rgb(var(--accent)) 0%, rgb(var(--accent) / 0.3) 60%, transparent 100%)" }}
            />

            {/* Header */}
            <div className="flex items-center justify-between px-5 py-4 border-b border-navy-700">
              <div className="flex items-center gap-2">
                <Settings className="w-4 h-4 text-brand-500" />
                <span className="text-white font-semibold text-sm">Settings</span>
              </div>
              <button
                onClick={() => setOpen(false)}
                className="text-gray-500 hover:text-gray-300 transition-colors"
                aria-label="Close settings"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Body */}
            <div className="p-5 space-y-5">
              <ProcessingSettings localOnly /><a href="/administration" className="text-brand-500 underline">Installation administration</a>
              {/* Scraping section */}
              {caps?.selenium && <div>
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">
                  Scraping
                </p>

                {/* Selenium toggle */}
                <label className="flex items-start gap-3 cursor-pointer select-none group">
                  <div
                    onClick={() => setSettings({ selenium: !settings.selenium })}
                    className={`w-9 h-5 rounded-full transition-all duration-200 relative shrink-0 mt-0.5 ${
                      settings.selenium ? "bg-brand-500" : "bg-gray-700 group-hover:bg-gray-600"
                    }`}
                  >
                    <span
                      className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow-sm transition-transform duration-200 ${
                        settings.selenium ? "translate-x-4" : ""
                      }`}
                    />
                  </div>
                  <div>
                    <span className="text-sm text-gray-300 group-hover:text-white transition-colors block">
                      Use Selenium (Chrome)
                    </span>
                    <span className="text-xs text-gray-600">Slower — requires ChromeDriver</span>
                  </div>
                </label>

              </div>}

              {/* Developer section */}
              <div>
                <p className="text-xs text-gray-500 font-medium uppercase tracking-wide mb-3">
                  Developer
                </p>
                <a
                  href="/api/docs"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2.5 w-full px-3 py-2 rounded-lg bg-gray-900 border border-gray-700 hover:border-brand-500 text-sm text-gray-300 hover:text-white transition-colors"
                >
                  <BookOpen className="w-4 h-4 text-brand-500 shrink-0" />
                  API documentation (Swagger)
                </a>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
