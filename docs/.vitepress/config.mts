import { defineConfig } from 'vitepress'

// Configuración del sitio de documentación de Syntax.
// Arranque: `pnpm --filter @syntax/docs docs:dev` (requiere `pnpm install` previo).
export default defineConfig({
  title: 'Syntax',
  description: 'Helpdesk con IA generativa (RAG + aprobación humana) — documentación del proyecto.',
  lang: 'es-ES',
  lastUpdated: true,
  cleanUrls: true,

  themeConfig: {
    nav: [
      { text: 'Inicio', link: '/' },
      { text: 'Empezar', link: '/getting-started' },
      { text: 'Arquitectura', link: '/architecture' },
      {
        text: 'Áreas',
        items: [
          { text: 'Backend', link: '/backend/' },
          { text: 'Frontend', link: '/frontend/' },
          { text: 'Contrato de API', link: '/reference/api-contract' },
          { text: 'ADR (decisiones)', link: '/reference/adr' },
          { text: 'Casos de uso', link: '/reference/casos-de-uso' },
        ],
      },
      { text: 'Método', link: '/guides/task-lifecycle' },
    ],

    sidebar: {
      '/': [
        {
          text: 'Introducción',
          items: [
            { text: 'Qué es Syntax', link: '/' },
            { text: 'Empezar', link: '/getting-started' },
            { text: 'Arquitectura', link: '/architecture' },
            { text: 'Glosario', link: '/reference/glossary' },
          ],
        },
        {
          text: 'Backend',
          collapsed: false,
          items: [
            { text: 'Visión general', link: '/backend/' },
            { text: 'Specs (fuente de verdad)', link: '/backend/specs' },
            { text: 'Guía de implementación', link: '/backend/implementation' },
          ],
        },
        {
          text: 'Frontend',
          collapsed: false,
          items: [{ text: 'Visión general', link: '/frontend/' }],
        },
        {
          text: 'Referencia',
          collapsed: false,
          items: [
            { text: 'ADR (decisiones)', link: '/reference/adr' },
            { text: 'Casos de uso', link: '/reference/casos-de-uso' },
            { text: 'Contrato de API', link: '/reference/api-contract' },
            { text: 'Modelo de datos', link: '/reference/data-model' },
            { text: 'RBAC', link: '/reference/rbac' },
            { text: 'RAG + ingestión', link: '/reference/rag' },
            { text: 'Agente + HITL', link: '/reference/agent-graph' },
            { text: 'Glosario', link: '/reference/glossary' },
          ],
        },
        {
          text: 'Método de trabajo',
          collapsed: false,
          items: [{ text: 'Task lifecycle', link: '/guides/task-lifecycle' }],
        },
      ],
    },

    outline: { level: [2, 3], label: 'En esta página' },
    docFooter: { prev: true, next: true },
    search: { provider: 'local' },
  },
})
