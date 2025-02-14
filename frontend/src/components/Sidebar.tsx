'use client';

import { useState } from 'react';
import Link from 'next/link';
import { 
  HomeIcon,
  DocumentIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  Square3Stack3DIcon,
  Cog6ToothIcon
} from '@heroicons/react/24/outline';

const getIconComponent = (iconName: string) => {
  const icons: { [key: string]: any } = {
    HomeIcon,
    DocumentIcon,
    Square3Stack3DIcon,
    Cog6ToothIcon,
  };
  return icons[iconName] || DocumentIcon;
};

export default function Sidebar() {
  const [isCollapsed, setIsCollapsed] = useState(false);

  const menuItems = [
  {
    "id": "b46186d5-7a48-43ca-b892-a5fd3e160cc8",
    "project_id": "6d235ca4-96fd-4ae9-8a19-e8238fca50f5",
    "menu_type": "left",
    "menu_items": [
      {
        "id": "page-1739379390267",
        "label": "Page 2",
        "url": "/pages/page-1739379390267",
        "icon": "page-icon",
        "sub_menu": []
      },
      {
        "id": "page-1739379399064",
        "label": "Page 2",
        "url": "/pages/page-1739379399064",
        "icon": "page-icon",
        "sub_menu": []
      }
    ],
    "style_config": {
      "backgroundColor": "#f5f5f5",
      "textColor": "#333333",
      "hoverColor": "#007bff"
    },
    "created_at": "2025-02-12T16:56:39.08944",
    "mainmenu_id": null
  }
]
    .flatMap(menu => menu.menu_items.map(item => ({
      name: item.label,
      icon: getIconComponent(item.icon || 'DocumentIcon'),
      path: item.url || '/',
    })));

  return (
    <aside className={`
      sidebar-transition fixed left-0 top-0 z-40 h-screen
      bg-white dark:bg-gray-800 shadow-lg
      ${isCollapsed ? 'w-[var(--sidebar-width-collapsed)]' : 'w-[var(--sidebar-width)]'}
      pt-[var(--topnav-height)]
    `}>
      <button
        onClick={() => setIsCollapsed(!isCollapsed)}
        className="absolute -right-3 top-20 bg-white dark:bg-gray-800 rounded-full p-1 shadow-lg"
      >
        {isCollapsed ? 
          <ChevronRightIcon className="w-5 h-5" /> : 
          <ChevronLeftIcon className="w-5 h-5" />
        }
      </button>
      
      <nav className="h-full px-3 py-4">
        <ul className="space-y-2">
          {menuItems.map((item) => (
            <li key={item.name}>
              <Link
                href={item.path}
                className="flex items-center p-2 text-gray-900 dark:text-white rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 group"
              >
                <item.icon className="w-6 h-6" />
                {!isCollapsed && (
                  <span className="ml-3">{item.name}</span>
                )}
              </Link>
            </li>
          ))}
        </ul>
      </nav>
    </aside>
  );
}