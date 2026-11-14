import { useCallback, useState } from "react";
import AppShell, { type StudioMode, type ViewKey } from "./components/AppShell";
import { ToastProvider } from "./components/ui";
import { useTheme } from "./hooks";
import About from "./views/About";
import Dashboard from "./views/Dashboard";
import Jobs from "./views/Jobs";
import Models from "./views/Models";
import Settings from "./views/Settings";
import Studio from "./views/Studio";
import System from "./views/System";
import Voices from "./views/Voices";
import Wizard from "./views/Wizard";

export default function App() {
  const [view, setView] = useState<ViewKey>("dashboard");
  const [studioMode, setStudioMode] = useState<StudioMode>("edit");
  const { theme, setTheme } = useTheme();

  const navigate = useCallback((v: ViewKey, mode?: StudioMode) => {
    setView(v);
    if (mode) setStudioMode(mode);
  }, []);

  return (
    <ToastProvider>
      <AppShell view={view} studioMode={studioMode} onNavigate={navigate} theme={theme} setTheme={setTheme}>
        {view === "dashboard" && <Dashboard onNavigate={navigate} />}
        {view === "studio" && <Studio mode={studioMode} onModeChange={setStudioMode} onNavigate={navigate} />}
        {view === "voices" && <Voices onNavigate={navigate} />}
        {view === "models" && <Models onNavigate={navigate} />}
        {view === "system" && <System onNavigate={navigate} />}
        {view === "wizard" && <Wizard onNavigate={navigate} />}
        {view === "jobs" && <Jobs onNavigate={navigate} />}
        {view === "settings" && <Settings onNavigate={navigate} theme={theme} setTheme={setTheme} />}
        {view === "about" && <About />}
      </AppShell>
    </ToastProvider>
  );
}