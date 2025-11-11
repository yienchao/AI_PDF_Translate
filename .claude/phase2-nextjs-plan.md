# Phase 2: Replace Streamlit with Next.js/React Frontend

## User Requirements (Confirmed)

### Architecture
- **Replace Streamlit completely** with Next.js/React
- Keep Streamlit files in codebase (don't delete, for reference)
- Full Next.js app with built-in API routes (Option B)

### Features to Include
- ✅ Same features as current Streamlit app (upload PDFs, translate, download)
- ✅ Keep Supabase authentication (working well)
- ✅ Keep translation history
- ✅ Drag-and-drop file upload interface
- ✅ Real-time progress bars
- ❌ No dark mode (not needed)
- ⏸️ Design framework TBD (Tailwind CSS recommended)

### Deployment
- Frontend: Vercel (recommended) or Render
- Backend: Keep Python translation logic, wrap with API

### Multi-User Question
**NEEDS CLARIFICATION**: User asked about multi-user support - two scenarios:
1. Multiple users from same enterprise - shared quota/history?
2. Different independent users - separate accounts?

Need to clarify which scenario before implementing.

---

## Technical Architecture

```
Next.js App (Vercel/Render)
├── Frontend: React components
│   ├── pages/
│   │   ├── index.tsx - Home with drag-drop upload
│   │   ├── translate.tsx - Translation progress
│   │   └── history.tsx - View past translations
│   └── components/
│       ├── FileUpload.tsx - Drag-drop component
│       ├── ProgressBar.tsx - Real-time progress
│       └── LanguageSelector.tsx
└── API Routes: /api/*
    ├── /api/translate - Upload & trigger translation
    ├── /api/status/:jobId - Check progress
    ├── /api/download/:filename - Download PDF
    └── /api/history - Get user history

Backend API (Flask/FastAPI wrapper)
├── Wraps existing Python code
├── Endpoints called by Next.js API routes
└── Returns JSON responses

Existing Python Code (KEEP AS-IS)
├── anthropic_translator.py - Core translation
├── api_key_manager.py - Key rotation
├── supabase_client.py - Database ops
├── translate_haiku_100.py - PDF processing
└── .env - API keys config
```

---

## Implementation Steps

### 1. Project Setup
```bash
# Create Next.js app
npx create-next-app@latest frontend --typescript --app --tailwind

# Install dependencies
cd frontend
npm install @supabase/supabase-js axios react-dropzone
```

### 2. Backend API Wrapper
Create Flask/FastAPI wrapper around existing Python code:
- **File**: `backend_api.py`
- **Purpose**: Expose Python translation logic as REST API
- **Endpoints**:
  - `POST /translate` - Upload PDFs, trigger translation
  - `GET /status/:jobId` - Get translation progress
  - `GET /download/:filename` - Serve translated PDF
  - `GET /history/:userId` - Get user translation history

### 3. Next.js API Routes
Create API routes that call Python backend:
- `app/api/translate/route.ts`
- `app/api/status/[jobId]/route.ts`
- `app/api/download/[filename]/route.ts`
- `app/api/history/route.ts`

### 4. Frontend Components
- **FileUpload.tsx**: Drag-and-drop with react-dropzone
- **ProgressBar.tsx**: Real-time translation progress
- **LanguageSelector.tsx**: Source/target language picker
- **TranslationHistory.tsx**: Display past translations

### 5. Pages
- **app/page.tsx**: Home page with file upload
- **app/translate/page.tsx**: Translation in progress
- **app/history/page.tsx**: View translation history
- **app/login/page.tsx**: Supabase authentication

### 6. Supabase Integration
- Use `@supabase/supabase-js` in Next.js
- Keep existing Supabase tables and auth setup
- Implement auth middleware for protected routes

---

## Code Reuse Strategy

### Keep Unchanged
✅ `anthropic_translator.py` - Core translation logic
✅ `api_key_manager.py` - API key rotation (5 keys, round-robin)
✅ `supabase_client.py` - Database operations
✅ `translate_haiku_100.py` - PDF processing with PyMuPDF
✅ `.env` - API keys configuration
✅ `app.py` - Keep but don't use (reference only)

### New Files to Create
- `backend_api.py` - Flask/FastAPI wrapper
- `frontend/` - Next.js project (entire directory)
- `frontend/.env.local` - Frontend environment variables

---

## Environment Variables

### Backend (.env) - Already exists
```
ANTHROPIC_API_KEY=...
ANTHROPIC_API_KEY_1=...
ANTHROPIC_API_KEY_2=...
ANTHROPIC_API_KEY_3=...
ANTHROPIC_API_KEY_4=...
SUPABASE_URL=...
SUPABASE_KEY=...
```

### Frontend (.env.local) - New
```
NEXT_PUBLIC_SUPABASE_URL=https://agexakhxckfvkwnflwxp.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
BACKEND_API_URL=http://localhost:5000  # or production URL
```

---

## Deployment Strategy

### Option A: Vercel (Recommended)
- **Frontend**: Deploy Next.js to Vercel (automatic from Git)
- **Backend**: Deploy Python API to Render or Railway
- **Pros**: Best Next.js hosting, fast CDN, easy setup
- **Cons**: Separate backend deployment

### Option B: Render (All-in-one)
- **Frontend + Backend**: Both on Render
- **Pros**: Single platform, easier management
- **Cons**: Slightly slower than Vercel for Next.js

---

## Progress Tracking

### Phase 2 Tasks
- [ ] Create Flask/FastAPI wrapper (`backend_api.py`)
- [ ] Set up Next.js project with TypeScript
- [ ] Implement file upload component with drag-drop
- [ ] Create translation API routes
- [ ] Implement real-time progress tracking
- [ ] Add Supabase authentication
- [ ] Create translation history page
- [ ] Test end-to-end workflow
- [ ] Deploy to Vercel/Render
- [ ] Configure CORS and environment variables

---

## Current Status: PLANNING PHASE

**User requested**: Save this plan for later implementation
**Next step**: User will confirm when ready to start Phase 2

---

## Questions to Resolve Before Implementation

1. **Multi-user scenario**: Same enterprise vs independent users?
2. **Design framework**: Use Tailwind CSS or another framework?
3. **Deployment preference**: Vercel or Render?
4. **Progress tracking method**: WebSocket or HTTP polling?

---

## Estimated Timeline

- Backend API wrapper: 1-2 hours
- Next.js setup + file upload: 2-3 hours
- API routes + integration: 2-3 hours
- Authentication + history: 1-2 hours
- Testing + deployment: 1-2 hours
- **Total**: ~7-12 hours

---

## Notes

- Streamlit app will remain in codebase but won't be used
- All existing Python translation logic stays unchanged
- Supabase setup remains the same
- API key rotation (5 keys) will continue working as-is
