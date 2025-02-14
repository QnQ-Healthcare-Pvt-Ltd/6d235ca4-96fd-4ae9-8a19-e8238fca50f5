'use client';

import { BellIcon, MoonIcon, SunIcon } from '@heroicons/react/24/outline';
import { useState } from 'react';

export default function TopNav() {
  const [isDarkMode, setIsDarkMode] = useState(false);

  const toggleDarkMode = () => {
    setIsDarkMode(!isDarkMode);
    document.documentElement.classList.toggle('dark');
  };

  return (
    <header className="fixed top-0 right-0 z-50 w-full h-[var(--topnav-height)] bg-white dark:bg-gray-800 shadow-sm">
      <div className="flex items-center justify-between h-full px-4">
        <div className="flex items-center">
          <span className="text-xl font-semibold text-gray-800 dark:text-white">
            OrangeHRM
          </span>
        </div>

        <div className="flex items-center space-x-4">
          <button className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
            <BellIcon className="w-6 h-6 text-gray-600 dark:text-gray-300" />
          </button>
          <button 
            onClick={toggleDarkMode}
            className="p-2 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            {isDarkMode ? (
              <SunIcon className="w-6 h-6 text-gray-600 dark:text-gray-300" />
            ) : (
              <MoonIcon className="w-6 h-6 text-gray-600 dark:text-gray-300" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
}