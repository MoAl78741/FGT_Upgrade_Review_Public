import { createContext, useContext, useState } from "react";


const STORAGE_KEY = "fgt-settings";

interface Settings {
  selenium: boolean;
}

function load(): Settings {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (raw) return {selenium: JSON.parse(raw).selenium === true};
  } catch {}
  return { selenium: false };
}

const SettingsContext = createContext<{
  settings: Settings;
  setSettings: (s: Partial<Settings>) => void;
}>({ settings: load(), setSettings: () => {} });

export function SettingsProvider({ children }: { children: React.ReactNode }) {
  const [settings, setSettingsState] = useState<Settings>(load);

  function setSettings(patch: Partial<Settings>) {
    setSettingsState((prev) => {
      const next = { ...prev, ...patch };
      localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      return next;
    });
  }

  return (
    <SettingsContext.Provider value={{ settings, setSettings }}>
      {children}
    </SettingsContext.Provider>
  );
}

export const useSettings = () => useContext(SettingsContext);
