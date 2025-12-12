# Loading Indicator Usage Guide

## Overview
The loading indicator system provides a beautiful animated loading state for your application during page transitions and async operations.

## Components Created

1. **LoadingIndicator** (`components/LoadingIndicator.tsx`)
   - Visual component with bouncing dots animation
   - Responsive and theme-aware (adapts to dark/light mode)

2. **LoadingProvider** (`lib/contexts/LoadingContext.tsx`)
   - Context provider for managing global loading state
   - Automatically detects route changes

## Setup (Already Done ✅)

The `LoadingProvider` has been added to your root layout, so it's ready to use!

## Usage Examples

### 1. Automatic Route Change Loading

The loading indicator automatically shows during Next.js route changes. No code needed!

```tsx
// Just use Next.js Link or router as normal
import Link from 'next/link';

export default function Navigation() {
  return (
    <nav>
      <Link href="/dashboard">Dashboard</Link>
      <Link href="/settings">Settings</Link>
    </nav>
  );
}
```

### 2. Manual Loading Control

Use the `useLoading` hook to manually control the loading state:

```tsx
'use client';

import { useLoading } from '@/lib/contexts/LoadingContext';

export default function MyComponent() {
  const { setLoading } = useLoading();

  const handleAsyncOperation = async () => {
    setLoading(true);
    try {
      await fetch('/api/data');
      // Process data...
    } finally {
      setLoading(false);
    }
  };

  return (
    <button onClick={handleAsyncOperation}>
      Load Data
    </button>
  );
}
```

### 3. Form Submission with Loading

```tsx
'use client';

import { useLoading } from '@/lib/contexts/LoadingContext';
import { useState } from 'react';

export default function ContactForm() {
  const { setLoading } = useLoading();
  const [formData, setFormData] = useState({ name: '', email: '' });

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    
    try {
      const response = await fetch('/api/contact', {
        method: 'POST',
        body: JSON.stringify(formData),
      });
      
      if (response.ok) {
        alert('Form submitted successfully!');
      }
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="text"
        value={formData.name}
        onChange={(e) => setFormData({ ...formData, name: e.target.value })}
        placeholder="Name"
      />
      <input
        type="email"
        value={formData.email}
        onChange={(e) => setFormData({ ...formData, email: e.target.value })}
        placeholder="Email"
      />
      <button type="submit">Submit</button>
    </form>
  );
}
```

### 4. API Call with Loading

```tsx
'use client';

import { useLoading } from '@/lib/contexts/LoadingContext';
import { useEffect, useState } from 'react';

export default function DataList() {
  const { setLoading } = useLoading();
  const [data, setData] = useState([]);

  useEffect(() => {
    const fetchData = async () => {
      setLoading(true);
      try {
        const response = await fetch('/api/items');
        const items = await response.json();
        setData(items);
      } catch (error) {
        console.error('Error fetching data:', error);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [setLoading]);

  return (
    <ul>
      {data.map((item) => (
        <li key={item.id}>{item.name}</li>
      ))}
    </ul>
  );
}
```

### 5. Programmatic Navigation with Loading

```tsx
'use client';

import { useLoading } from '@/lib/contexts/LoadingContext';
import { useRouter } from 'next/navigation';

export default function NavigationButton() {
  const { setLoading } = useLoading();
  const router = useRouter();

  const handleNavigate = () => {
    setLoading(true);
    router.push('/dashboard');
    // Loading will auto-hide when route changes
  };

  return (
    <button onClick={handleNavigate}>
      Go to Dashboard
    </button>
  );
}
```

### 6. Using Just the LoadingIndicator Component

You can also use the LoadingIndicator component directly without the context:

```tsx
import LoadingIndicator from '@/components/LoadingIndicator';

export default function MyPage() {
  const [loading, setLoading] = useState(true);

  if (loading) {
    return <LoadingIndicator />;
  }

  return <div>Content loaded!</div>;
}
```

### 7. Custom Loading Component

Create a custom loading component based on LoadingIndicator:

```tsx
import React from 'react';

const CustomLoader: React.FC<{ message?: string }> = ({ message = 'Loading...' }) => {
  return (
    <div className="w-full h-screen flex flex-col items-center justify-center bg-transparent">
      <div className="flex items-center gap-3 text-blue-600 dark:text-blue-400 mb-4">
        <div className="w-3 h-3 rounded-full bg-current animate-bounce [animation-delay:-0.3s]"></div>
        <div className="w-3 h-3 rounded-full bg-current animate-bounce [animation-delay:-0.15s]"></div>
        <div className="w-3 h-3 rounded-full bg-current animate-bounce"></div>
      </div>
      <p className="text-muted-foreground text-sm">{message}</p>
    </div>
  );
};

export default CustomLoader;
```

## API Reference

### useLoading Hook

```tsx
const { isLoading, setLoading } = useLoading();
```

**Returns:**
- `isLoading`: `boolean` - Current loading state
- `setLoading`: `(loading: boolean) => void` - Function to set loading state

### LoadingIndicator Component

```tsx
<LoadingIndicator />
```

**Props:** None

**Features:**
- Animated bouncing dots
- Theme-aware colors (blue-600 in light mode, blue-400 in dark mode)
- Centered layout
- Accessible (includes sr-only text)

## Customization

### Change Colors

Edit `components/LoadingIndicator.tsx`:

```tsx
// Change from blue to purple
<div className="flex items-center gap-3 text-purple-600 dark:text-purple-400">
```

### Change Size

```tsx
// Larger dots
<div className="w-4 h-4 rounded-full bg-current animate-bounce"></div>

// Smaller dots
<div className="w-2 h-2 rounded-full bg-current animate-bounce"></div>
```

### Change Animation Speed

Add to your `tailwind.config.js`:

```js
module.exports = {
  theme: {
    extend: {
      animation: {
        'bounce-slow': 'bounce 1.5s infinite',
        'bounce-fast': 'bounce 0.5s infinite',
      },
    },
  },
};
```

Then use:
```tsx
<div className="animate-bounce-slow"></div>
```

## Best Practices

1. **Always use finally**: When manually controlling loading, always use try-finally to ensure loading stops even if there's an error

2. **Don't nest loading states**: Avoid setting loading=true multiple times without setting it to false

3. **Keep it brief**: Only show loading for operations that take > 300ms

4. **Provide feedback**: For long operations, consider showing progress or a message

5. **Handle errors**: Always handle errors gracefully and stop loading

## Troubleshooting

### Loading indicator doesn't show
- Make sure you're calling `setLoading(true)`
- Check that LoadingProvider is in your layout
- Verify you're using the hook in a client component

### Loading never stops
- Ensure you're calling `setLoading(false)` in a finally block
- Check for errors that might prevent the finally block from running

### Multiple loading indicators
- Only one loading indicator shows at a time (global state)
- If you need multiple, use the LoadingIndicator component directly
