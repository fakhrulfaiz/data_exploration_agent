# AuthContext Usage Guide

## Overview
The `AuthContext` provides authentication state management using Supabase throughout your Next.js application.

## Setup (Already Done ✅)

The `AuthProvider` has been added to your root layout (`app/layout.tsx`), wrapping your entire application:

```tsx
<AuthProvider>
  {children}
</AuthProvider>
```

## Using the useAuth Hook

### Basic Usage

In any client component, import and use the `useAuth` hook:

```tsx
'use client';

import { useAuth } from '@/lib/contexts/AuthContext';

export default function MyComponent() {
  const { user, session, loading, signOut } = useAuth();

  if (loading) {
    return <div>Loading...</div>;
  }

  if (!user) {
    return <div>Please sign in</div>;
  }

  return (
    <div>
      <p>Welcome, {user.email}!</p>
      <button onClick={signOut}>Sign Out</button>
    </div>
  );
}
```

## Available Properties

### `user`
- Type: `User | null`
- The current authenticated user object from Supabase
- Contains: `id`, `email`, `user_metadata`, etc.

### `session`
- Type: `Session | null`
- The current session object
- Contains: `access_token`, `refresh_token`, `expires_at`, etc.

### `loading`
- Type: `boolean`
- `true` while checking authentication status
- `false` once auth state is determined

### `signOut`
- Type: `() => Promise<void>`
- Function to sign out the current user
- Automatically clears session and updates state

## Common Use Cases

### 1. Protecting Routes

```tsx
'use client';

import { useAuth } from '@/lib/contexts/AuthContext';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function ProtectedPage() {
  const { user, loading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.push('/login');
    }
  }, [user, loading, router]);

  if (loading) return <div>Loading...</div>;
  if (!user) return null;

  return <div>Protected Content</div>;
}
```

### 2. Conditional Rendering

```tsx
'use client';

import { useAuth } from '@/lib/contexts/AuthContext';

export default function Header() {
  const { user, signOut } = useAuth();

  return (
    <header>
      {user ? (
        <div>
          <span>{user.email}</span>
          <button onClick={signOut}>Sign Out</button>
        </div>
      ) : (
        <a href="/login">Sign In</a>
      )}
    </header>
  );
}
```

### 3. Getting User Info

```tsx
'use client';

import { useAuth } from '@/lib/contexts/AuthContext';

export default function UserProfile() {
  const { user } = useAuth();

  if (!user) return null;

  return (
    <div>
      <h2>Profile</h2>
      <p>Email: {user.email}</p>
      <p>User ID: {user.id}</p>
      <p>Created: {new Date(user.created_at).toLocaleDateString()}</p>
      {user.user_metadata?.full_name && (
        <p>Name: {user.user_metadata.full_name}</p>
      )}
    </div>
  );
}
```

### 4. Making Authenticated API Calls

```tsx
'use client';

import { useAuth } from '@/lib/contexts/AuthContext';
import { useEffect, useState } from 'react';

export default function DataComponent() {
  const { session } = useAuth();
  const [data, setData] = useState(null);

  useEffect(() => {
    if (session?.access_token) {
      fetch('/api/data', {
        headers: {
          'Authorization': `Bearer ${session.access_token}`
        }
      })
        .then(res => res.json())
        .then(setData);
    }
  }, [session]);

  return <div>{/* Render data */}</div>;
}
```

### 5. Sign Out with Confirmation

```tsx
'use client';

import { useAuth } from '@/lib/contexts/AuthContext';

export default function SignOutButton() {
  const { signOut } = useAuth();

  const handleSignOut = async () => {
    if (confirm('Are you sure you want to sign out?')) {
      try {
        await signOut();
        // Optionally redirect
        window.location.href = '/';
      } catch (error) {
        console.error('Error signing out:', error);
        alert('Failed to sign out');
      }
    }
  };

  return <button onClick={handleSignOut}>Sign Out</button>;
}
```

## Example: Already Implemented

The `Sidebar` component already uses the `AuthContext`:

```tsx
import { useAuth } from '@/lib/contexts/AuthContext';

const Sidebar = () => {
  const { user, signOut } = useAuth();

  return (
    <div>
      {/* ... other sidebar content ... */}
      
      <button onClick={async () => { await signOut(); }}>
        <LogOut className="w-4 h-4" />
        <span>Sign out{user?.email ? ` (${user.email})` : ''}</span>
      </button>
    </div>
  );
};
```

## Important Notes

1. **Client Components Only**: The `useAuth` hook can only be used in client components (with `'use client'` directive)

2. **Loading State**: Always check the `loading` state before making decisions based on `user` or `session`

3. **Error Handling**: The `signOut` function can throw errors, so wrap it in try-catch when needed

4. **Automatic Updates**: The context automatically updates when auth state changes (login, logout, token refresh)

5. **SSR Compatibility**: The provider is designed to work with Next.js SSR/SSG patterns

## Troubleshooting

### "useAuth must be used within an AuthProvider"
- Make sure `AuthProvider` is wrapping your component tree in `app/layout.tsx`

### User is null after login
- Check that Supabase is properly configured with environment variables
- Verify `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY` are set

### Session not persisting
- Supabase automatically handles session persistence via localStorage
- Make sure cookies are enabled in the browser
