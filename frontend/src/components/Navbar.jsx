import { Link, useLocation } from 'react-router-dom'

const links = [
  { to: '/', label: 'Dashboard' },
  { to: '/conversations', label: 'Conversations' },
  { to: '/triggers', label: 'Triggers' },
  { to: '/outbound', label: 'Outbound' },
  { to: '/stats', label: 'Stats' },
  { to: '/settings', label: 'Settings' },
]

export default function Navbar() {
  const { pathname } = useLocation()
  return (
    <nav className="bg-gray-900 text-white px-6 py-3 flex items-center gap-6">
      <span className="font-bold text-lg mr-4">IG Bot</span>
      {links.map(({ to, label }) => (
        <Link
          key={to}
          to={to}
          className={`text-sm hover:text-purple-400 transition-colors ${
            pathname === to ? 'text-purple-400 font-semibold' : 'text-gray-300'
          }`}
        >
          {label}
        </Link>
      ))}
    </nav>
  )
}
