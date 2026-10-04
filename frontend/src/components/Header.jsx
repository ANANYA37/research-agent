import { Bell, Brain, LogOut, MessageSquare, Archive, Settings as SettingsIcon } from 'lucide-react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { api } from '../api/client';
import ThemeToggle from './ThemeToggle';
import { useAuth } from '../auth/AuthContext';
import './Header.css';

export default function Header() {
  const location = useLocation();
  const { user, logout } = useAuth();
  const { data: watches = [] } = useQuery({ queryKey: ['watchlists', user?.id], queryFn: api.watchlists, enabled: !!user, refetchInterval: 30000 });
  const unread = watches.filter((watch) => watch.unread).length;
  const accountName = user?.email || 'Your account';
  const initial = (user?.email?.[0] || 'U').toUpperCase();
  const links = [
    { to: '/chat', label: 'Chat', icon: MessageSquare, active: ['/chat', '/research'].includes(location.pathname) },
    { to: '/library', label: 'Library', icon: Archive, active: location.pathname.startsWith('/library') || location.pathname.startsWith('/reports/') },
    { to: '/watchlists', label: 'Watchlists', icon: Bell, active: location.pathname.startsWith('/watchlists') },
    { to: '/settings', label: 'Settings', icon: SettingsIcon, active: location.pathname === '/settings' },
  ];

  return (
    <header className="workspace-header">
      <Link to="/chat" className="workspace-brand" aria-label="ResearchAgent home">
        <span className="workspace-brand-symbol"><Brain size={21} strokeWidth={1.6} /></span>
        <span className="workspace-brand-copy"><span className="workspace-brand-name">Research<span>Agent</span></span><span className="workspace-brand-caption">A SPACE FOR DISCOVERY</span></span>
      </Link>
      <nav className="workspace-navigation" aria-label="Main navigation">
        {links.map(({ to, label, icon, active }) => {
          const IconComponent = icon;
          return <NavLink key={to} to={to} className={active ? 'workspace-nav-link is-current' : 'workspace-nav-link'} aria-current={active ? 'page' : undefined}><IconComponent size={15} strokeWidth={1.7} />{label}{to === '/watchlists' && unread > 0 && <span className="workspace-unread" aria-label={`${unread} watchlists with unread updates`}>{unread}</span>}</NavLink>;
        })}
      </nav>
      <div className="workspace-header-tools">
        <ThemeToggle />
        <span className="workspace-header-divider" aria-hidden="true" />
        <Link to="/settings" className="workspace-account-avatar" title={accountName} aria-label={`Account settings for ${accountName}`}>{initial}</Link>
        <button type="button" className="workspace-signout" onClick={logout} title="Sign out" aria-label="Sign out"><LogOut size={16} /></button>
      </div>
    </header>
  );
}
