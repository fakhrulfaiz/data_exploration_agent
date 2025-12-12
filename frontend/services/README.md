# Frontend Services

This directory contains all API client services for communicating with the backend.

## 📁 Structure

```
services/
├── api/                      # API service classes
│   ├── conversation.service.ts  # Conversation/thread management
│   ├── agent.service.ts         # Agent operations
│   ├── data.service.ts          # DataFrame operations
│   ├── graph.service.ts         # Graph execution with SSE streaming
│   ├── explorer.service.ts      # Explorer data fetching
│   └── visualization.service.ts # Visualization data fetching
├── client.ts                 # Base API client (fetch wrapper)
├── endpoints.ts              # API endpoint constants
└── index.ts                  # Central exports
```

## 🚀 Usage

### Import Services

```typescript
import { 
  ConversationService, 
  AgentService, 
  DataService, 
  GraphService,
  ExplorerService,
  VisualizationService 
} from '@/services';
```

### Example: Create a Conversation

```typescript
const response = await ConversationService.createConversation({
  title: 'My Analysis',
  initial_message: 'Analyze sales data'
});
```

### Example: Stream Graph Execution

```typescript
const eventSource = GraphService.streamResponse(threadId, {
  onMessage: (data) => console.log('Received:', data),
  onError: (error) => console.error('Error:', error),
  onComplete: () => console.log('Stream complete')
});

// Close the stream when done
eventSource.close();
```

## ⚙️ Configuration

### Environment Variables

Create a `.env.local` file in the `frontend/` directory:

```env
# Backend API URL
NEXT_PUBLIC_API_URL=http://localhost:8000
```

**Important:** The `NEXT_PUBLIC_` prefix is required for Next.js to expose this variable to the browser.

## 🔒 Next.js Compatibility

### Client-Side Only

All services in this directory are **client-side only** because they use:
- `fetch` API
- `EventSource` for Server-Sent Events (SSE)
- Browser-specific APIs

### Usage in Components

✅ **Correct** - Use in Client Components:

```typescript
'use client';

import { ConversationService } from '@/services';

export default function MyComponent() {
  const handleCreate = async () => {
    const result = await ConversationService.createConversation({...});
  };
  
  return <button onClick={handleCreate}>Create</button>;
}
```

❌ **Incorrect** - Don't use in Server Components:

```typescript
// This will NOT work - no 'use client' directive
import { ConversationService } from '@/services';

export default async function ServerComponent() {
  // ❌ This will fail!
  const data = await ConversationService.listConversations();
  return <div>{data}</div>;
}
```

### Server-Side Alternative

If you need to fetch data on the server (for SSR/SSG), use `fetch` directly in Server Components or Route Handlers:

```typescript
// app/api/conversations/route.ts
export async function GET() {
  const response = await fetch('http://localhost:8000/conversation');
  const data = await response.json();
  return Response.json(data);
}
```

## 📝 Type Safety

All services are fully typed with TypeScript interfaces from `@/types`. The types mirror the backend Pydantic schemas for consistency.

## 🔗 Backend Endpoints

Services communicate with these backend endpoints:

- **Conversation**: `/conversation/*`
- **Agent**: `/agent/*`
- **Data**: `/data/*`
- **Graph**: `/graph/*` and `/graph/stream/*`

See `endpoints.ts` for the complete list.
