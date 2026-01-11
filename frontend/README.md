# React + Vite

Questo modello fornisce una configurazione minima per far funzionare React in Vite con HMR e alcune regole ESLint.

Attualmente sono disponibili due plugin ufficiali:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) utilizza [Babel](https://babeljs.io/) (o [oxc](https://oxc.rs) quando utilizzato in [rolldown-vite](https://vite.dev/guide/rolldown)) per l'aggiornamento rapido
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) utilizza [SWC](https://swc.rs/) per l'aggiornamento rapido

## Compilatore React

Il compilatore React non è abilitato su questo template a causa del suo impatto sulle prestazioni di sviluppo e build. Per aggiungerlo, consulta [questa documentazione](https://react.dev/learn/react-compiler/installation).

## Espansione della configurazione di ESLint

Se stai sviluppando un'applicazione di produzione, ti consigliamo di utilizzare TypeScript con le regole di lint basate sui tipi abilitate. Consulta il [template TS](https://github.com/vitejs/vite/tree/main/packages/create-vite/template-react-ts) per informazioni su come integrare TypeScript e [`typescript-eslint`](https://typescript-eslint.io) nel tuo progetto.