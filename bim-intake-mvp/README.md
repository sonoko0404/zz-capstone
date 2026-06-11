# BIM Intake MVP

Vue 3 + Vite + TypeScript frontend for submitting BIM-related requests. The MVP now uses Element Plus, email-only mock login, sidebar navigation, Jira-style draft generation, mock ITO/BIM linked ticket keys, and `localStorage` persistence.

## Local Development

```bash
npm install
npm run dev
```

## Build

```bash
npm run build
```

The production output is generated in `dist/`.

## Environment

Copy `.env.example` to `.env.local` if a submit API becomes available:

```bash
VITE_INTAKE_API_URL=https://example.com/api/intake
VITE_AUTH_API_URL=https://example.com/api/auth/email
```

When these values are empty, the app uses local mock login and submit flows.

## Vercel

The project includes `vercel.json` for Vite static deployment:

- Build command: `npm run build`
- Output directory: `dist`
- Framework: `vite`

Future deployment from this project root:

```bash
vercel
vercel --prod
```
