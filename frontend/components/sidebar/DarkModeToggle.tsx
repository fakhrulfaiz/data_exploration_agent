'use client';

import React from 'react';
import { Moon, Sun, Monitor } from 'lucide-react';
import { useTheme } from 'next-themes';

interface DarkModeToggleProps {
  className?: string;
  size?: 'sm' | 'md' | 'lg';
}

const DarkModeToggle: React.FC<DarkModeToggleProps> = ({
  className = '',
  size = 'md'
}) => {
  const { theme, setTheme } = useTheme();

  const handleToggle = () => {
    // Cycle through: light → dark → system → light
    if (theme === 'light') {
      setTheme('dark');
    } else if (theme === 'dark') {
      setTheme('system');
    } else {
      setTheme('light');
    }
  };

  const sizeClasses = {
    sm: 'w-8 h-8',
    md: 'w-10 h-10',
    lg: 'w-12 h-12'
  };

  const iconSizes = {
    sm: 'w-4 h-4',
    md: 'w-5 h-5',
    lg: 'w-6 h-6'
  };

  const getIcon = () => {
    if (theme === 'dark') {
      return <Sun className={iconSizes[size]} />;
    } else if (theme === 'system') {
      return <Monitor className={iconSizes[size]} />;
    } else {
      return <Moon className={iconSizes[size]} />;
    }
  };

  const getLabel = () => {
    if (theme === 'dark') {
      return 'Switch to system theme';
    } else if (theme === 'system') {
      return 'Switch to light mode';
    } else {
      return 'Switch to dark mode';
    }
  };

  return (
    <button
      onClick={handleToggle}
      className={`
        ${sizeClasses[size]}
        flex items-center justify-center
        rounded-lg
        transition-all duration-200
        hover:scale-105
        focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2
        bg-muted text-foreground hover:bg-accent
        ${className}
      `}
      aria-label={getLabel()}
      title={getLabel()}
    >
      {getIcon()}
    </button>
  );
};

export default DarkModeToggle;
