// Config principale per il frontend.
// Usa la variabile d'ambiente VITE_API_URL fornita da Vite se presente,
// altrimenti usa l'URL di fallback (deployment pubblico).
// Per sviluppo impostare VITE_API_URL in `.env` o `.env.local`.
export const API_BASE_URL = import.meta.env.VITE_API_URL || "https://licensechecker-license-checker-tool.hf.space";
