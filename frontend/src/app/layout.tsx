import type { Metadata } from 'next'
import { Inter } from 'next/font/google'
import './globals.css'
import Sidebar from '@/components/Sidebar'
import TopNav from '@/components/TopNav'

const inter = Inter({ subsets: ['latin'] })

export const metadata: Metadata = {
  title: 'OrangeHRM',
  description: 'OrangeHRM Dashboard',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className={inter.className}>
        <TopNav />
        <Sidebar />
        <main className="sidebar-transition pl-[var(--sidebar-width)] pt-[var(--topnav-height)] min-h-screen">
          <div className="p-4">
            {children}
          </div>
        </main>
      </body>
    </html>
  )
}