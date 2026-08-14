import { useEffect, useState } from "react";

/**
 * Estado de conexión de red del navegador. Se inicializa optimista (`true`) y se actualiza mediante los
 * eventos `online`/`offline` (el `setState` vive en los handlers, no en el cuerpo del efecto).
 */
export function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(true);

  useEffect(() => {
    const goOnline = () => setOnline(true);
    const goOffline = () => setOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, []);

  return online;
}
