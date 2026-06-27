import { useNavigate } from 'react-router-dom';
import { Activity, Mail, Newspaper, Settings, Zap } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { useHealth } from '../api/hooks';
import { Card } from '../components/ui/Card';
import { Rise, Stagger } from '../components/ui/motion';
import { useAppLocale } from '../lib/useAppLocale';
import { haptic } from '../telegram/webapp';

interface MoreLink {
  to: string;
  label: { en: string; ru: string };
  description: { en: string; ru: string };
  icon: LucideIcon;
}

const LINKS: MoreLink[] = [
  { to: '/inbox', label: { en: 'Inbox', ru: 'Почта' }, description: { en: 'Messages and triage', ru: 'Входящие и письма' }, icon: Mail },
  { to: '/news', label: { en: 'News', ru: 'Новости' }, description: { en: 'Topics and digests', ru: 'Темы и дайджесты' }, icon: Newspaper },
  { to: '/automations', label: { en: 'Automations', ru: 'Автоматизации' }, description: { en: 'Scheduled workflows', ru: 'Сценарии по расписанию' }, icon: Zap },
  { to: '/runs', label: { en: 'Agent runs', ru: 'Запуски агента' }, description: { en: 'Work log', ru: 'Журнал работы' }, icon: Activity },
  { to: '/settings', label: { en: 'Settings', ru: 'Настройки' }, description: { en: 'Profile and connections', ru: 'Профиль и подключения' }, icon: Settings },
];

export default function MorePage() {
  const navigate = useNavigate();
  const health = useHealth();
  const locale = useAppLocale();

  return (
    <Stagger>
      <div className="grid grid-cols-2 gap-3">
        {LINKS.map((link) => {
          const Icon = link.icon;
          const label = link.label[locale];
          const description = link.description[locale];
          return (
            <Rise key={link.to}>
              <Card
                className="card-strong h-full px-4 py-4"
                onClick={() => {
                  haptic('light');
                  navigate(link.to);
                }}
                aria-label={label}
              >
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[var(--accent-soft)]">
                  <Icon size={18} className="text-accent-text" strokeWidth={1.8} />
                </div>
                <p className="mt-3 text-[14.5px] font-semibold text-ink">{label}</p>
                <p className="mt-0.5 text-[12px] leading-snug text-hint">{description}</p>
              </Card>
            </Rise>
          );
        })}
      </div>

      <Rise>
        <div className="mt-10 flex flex-col items-center gap-1.5 text-center">
          <span className="font-display text-[15px] font-light tracking-[0.06em] text-hint">Lumi</span>
          <span className="tnum text-[11.5px] text-hint">
            {health.data
              ? `${health.data.env} · v${health.data.version}`
              : locale === 'ru'
                ? 'личный AI-ассистент'
                : 'personal AI assistant'}
          </span>
        </div>
      </Rise>
    </Stagger>
  );
}
