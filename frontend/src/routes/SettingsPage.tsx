import { useEffect, useState } from 'react';
import { Check, Minus } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../api/client';
import { openExternalLink } from '../telegram/webapp';
import { qk, useConnectYandex, useDisconnectGoogle, useDisconnectYandex, useHealth, usePatchSettings, useRunPoller, useSettings } from '../api/hooks';
import type { GoogleStatus } from '../api/types';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { FieldLabel, Input, Select } from '../components/ui/Field';
import { SectionHeader } from '../components/ui/SectionHeader';
import { SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { formatRelative } from '../lib/format';
import { COMMON_TIMEZONES } from '../lib/labels';

function BoolRow({ label, value }: { label: string; value: boolean }) {
  return (
    <div className="flex min-h-[44px] items-center justify-between gap-3 px-4 py-2">
      <span className="text-[13.5px] text-ink">{label}</span>
      {value ? (
        <Check size={16} className="shrink-0 text-success" />
      ) : (
        <Minus size={16} className="shrink-0 text-hint" />
      )}
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex min-h-[44px] items-center justify-between gap-3 px-4 py-2">
      <span className="text-[13.5px] text-hint">{label}</span>
      <span className="tnum min-w-0 truncate text-[13.5px] font-medium text-ink">{value}</span>
    </div>
  );
}

const GOOGLE_STATUS_LABELS: Record<GoogleStatus['status'], { label: string; className: string }> = {
  connected: { label: 'Подключен', className: 'bg-[var(--success-soft)] text-success' },
  disconnected: { label: 'Не подключен', className: 'bg-[var(--secondary-bg)] text-hint' },
  error: { label: 'Ошибка', className: 'bg-[var(--danger-soft)] text-danger' },
  needs_reauth: { label: 'Нужна повторная авторизация', className: 'bg-[var(--danger-soft)] text-danger' },
};

function shortScope(scope: string): string {
  return scope.replace('https://www.googleapis.com/auth/', '');
}

export default function SettingsPage() {
  const settingsQuery = useSettings();
  const healthQuery = useHealth();
  const patchSettings = usePatchSettings();
  const disconnectGoogle = useDisconnectGoogle();
  const connectYandex = useConnectYandex();
  const disconnectYandex = useDisconnectYandex();
  const [yandexLogin, setYandexLogin] = useState('');
  const [yandexPassword, setYandexPassword] = useState('');
  const [confirmYandexDisconnect, setConfirmYandexDisconnect] = useState(false);
  const [yandexSyncRunId, setYandexSyncRunId] = useState<string | null>(null);
  const [googleConnecting, setGoogleConnecting] = useState(false);
  const [confirmDisconnect, setConfirmDisconnect] = useState(false);
  const { show } = useToast();

  if (settingsQuery.isPending) return <SkeletonList count={4} lines={3} />;
  if (settingsQuery.isError) {
    return <ErrorState message="Не удалось загрузить настройки." onRetry={() => void settingsQuery.refetch()} />;
  }

  const { user, google, yandex } = settingsQuery.data;
  const displayName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || 'Пользователь';
  const initial = (user.first_name ?? user.username ?? 'L').slice(0, 1).toUpperCase();
  const timezones = COMMON_TIMEZONES.includes(user.timezone)
    ? COMMON_TIMEZONES
    : [user.timezone, ...COMMON_TIMEZONES];
  const googleStatus = GOOGLE_STATUS_LABELS[google.status];
  const yandexStatus = GOOGLE_STATUS_LABELS[yandex.status];
  const yandexConnected = yandex.status === 'connected' || yandex.status === 'needs_reauth';
  const yandexSyncPoller = useRunPoller(yandexSyncRunId, [qk.eventsAll, qk.settings, qk.today]);
  useEffect(() => {
    if (yandexSyncRunId === null) return;
    if (yandexSyncPoller.status === 'completed') {
      show('Календарь синхронизирован — события уже в расписании', 'success');
      setYandexSyncRunId(null);
    } else if (yandexSyncPoller.status === 'failed' || yandexSyncPoller.status === 'timeout') {
      show('Синхронизация не удалась — попробуй кнопку на странице Календарь', 'error');
      setYandexSyncRunId(null);
    }
  }, [yandexSyncPoller.status, yandexSyncRunId, show]);

  const queryClientForGoogle = useQueryClient();
  const handleGoogleConnect = () => {
    api
      .getGoogleAuthUrl()
      .then(({ url }) => {
        setGoogleConnecting(true);
        openExternalLink(url);
      })
      .catch((e: unknown) => {
        const code = e instanceof ApiError ? e.error : '';
        show(
          code === 'client_secret_missing'
            ? 'Сначала положи client_secret.json в data/secrets (см. доку)'
            : code === 'public_url_missing'
              ? 'Нужен APP_PUBLIC_URL (HTTPS-туннель)'
              : 'Не удалось начать подключение',
          'error',
        );
      });
  };
  useEffect(() => {
    if (!googleConnecting) return;
    if (google.status === 'connected') {
      setGoogleConnecting(false);
      show('Google подключен — синхронизирую календарь', 'success');
      return;
    }
    const interval = setInterval(() => {
      void queryClientForGoogle.invalidateQueries({ queryKey: qk.settings });
    }, 3000);
    const stop = setTimeout(() => setGoogleConnecting(false), 180_000);
    return () => {
      clearInterval(interval);
      clearTimeout(stop);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [googleConnecting, google.status]);

  const handleYandexConnect = () => {
    connectYandex.mutate(
      { username: yandexLogin.trim(), app_password: yandexPassword.trim() },
      {
        onSuccess: (data) => {
          setYandexLogin('');
          setYandexPassword('');
          show('Подключено! Синхронизирую события…', 'success');
          if (data.run_id) setYandexSyncRunId(data.run_id);
        },
        onError: () => show('Яндекс отклонил логин или пароль приложения', 'error'),
      },
    );
  };

  const handleTimezone = (timezone: string) => {
    patchSettings.mutate(
      { timezone },
      {
        onSuccess: () => show('Часовой пояс сохранён', 'success'),
        onError: () => show('Не удалось сохранить', 'error'),
      },
    );
  };

  return (
    <Stagger>
      {/* Profile */}
      <Rise>
        <Card className="card-strong p-4">
          <div className="flex items-center gap-3.5">
            <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-[var(--accent-soft)] font-display text-[18px] text-accent-text">
              {initial}
            </div>
            <div className="min-w-0">
              <p className="truncate text-[15.5px] font-semibold text-ink">{displayName}</p>
              {user.username && <p className="truncate text-[13px] text-hint">@{user.username}</p>}
            </div>
          </div>
          <label className="mt-4 block">
            <FieldLabel>Часовой пояс</FieldLabel>
            <Select
              value={user.timezone}
              onChange={handleTimezone}
              options={timezones.map((tz) => ({ value: tz, label: tz }))}
            />
          </label>
        </Card>
      </Rise>

      {/* Google */}
      <Rise>
        <SectionHeader title="Google" />
        <Card className="card-strong !p-0">
          <div className="flex min-h-[48px] items-center justify-between gap-3 px-4 py-2.5">
            <span className="text-[13.5px] text-ink">Статус</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-medium ${googleStatus.className}`}>
              {googleStatus.label}
            </span>
          </div>
          <div className="divide-y divide-[var(--hairline)] border-t border-hairline">
            <BoolRow label="Gmail" value={google.gmail_available} />
            <BoolRow label="Calendar" value={google.calendar_available} />
            <InfoRow
              label="Последняя синхронизация"
              value={google.last_sync_at ? formatRelative(google.last_sync_at) : '—'}
            />
          </div>
          {google.scopes.length > 0 && (
            <div className="flex flex-wrap gap-1.5 border-t border-hairline px-4 py-3">
              {google.scopes.map((scope) => (
                <span key={scope} className="rounded-full bg-[var(--secondary-bg)] px-2.5 py-1 font-mono text-[11px] text-hint">
                  {shortScope(scope)}
                </span>
              ))}
            </div>
          )}
          {google.last_error && (
            <p className="border-t border-hairline px-4 py-3 text-[12.5px] leading-snug text-danger">{google.last_error}</p>
          )}
          <div className="border-t border-hairline px-4 py-3.5">
            {google.status === 'connected' || google.status === 'needs_reauth' || google.status === 'error' ? (
              confirmDisconnect ? (
                <div className="flex items-center gap-2.5">
                  <span className="mr-auto text-[13px] text-danger">Отключить Google?</span>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmDisconnect(false)}>
                    Отмена
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    busy={disconnectGoogle.isPending}
                    onClick={() =>
                      disconnectGoogle.mutate(undefined, {
                        onSuccess: () => {
                          setConfirmDisconnect(false);
                          show('Google отключен', 'success');
                        },
                        onError: () => show('Не удалось отключить', 'error'),
                      })
                    }
                  >
                    Отключить
                  </Button>
                </div>
              ) : (
                <Button size="sm" variant="danger" onClick={() => setConfirmDisconnect(true)}>
                  Отключить
                </Button>
              )
            ) : (
              <div>
                <p className="text-[13px] leading-relaxed text-hint">
                  Lumi получит доступ к почте (только чтение) и календарю. Один тап —
                  откроется Google, разреши доступ и вернись сюда.
                </p>
                <Button
                  className="mt-3"
                  busy={googleConnecting}
                  onClick={handleGoogleConnect}
                >
                  Подключить Google
                </Button>
                {googleConnecting && (
                  <p className="mt-2 text-[12.5px] text-hint">
                    Жду подтверждения в Google… статус обновится сам.
                  </p>
                )}
              </div>
            )}
          </div>
        </Card>
      </Rise>

      {/* Yandex Calendar */}
      <Rise>
        <SectionHeader title="Яндекс.Календарь" />
        <Card className="card-strong !p-0">
          <div className="flex min-h-[48px] items-center justify-between gap-3 px-4 py-2.5">
            <span className="text-[13.5px] text-ink">Статус</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-medium ${yandexStatus.className}`}>
              {yandexStatus.label}
            </span>
          </div>
          {yandexConnected ? (
            <>
              <div className="divide-y divide-[var(--hairline)] border-t border-hairline">
                <InfoRow label="Аккаунт" value={yandex.username ?? '—'} />
                <InfoRow
                  label="Последняя синхронизация"
                  value={yandex.last_sync_at ? formatRelative(yandex.last_sync_at) : '—'}
                />
                <InfoRow label="Доступ" value="только чтение (CalDAV)" />
              </div>
              {yandex.last_error && (
                <p className="border-t border-hairline px-4 py-3 text-[12.5px] leading-snug text-danger">
                  {yandex.last_error}
                </p>
              )}
              <div className="border-t border-hairline px-4 py-3.5">
                {confirmYandexDisconnect ? (
                  <div className="flex items-center gap-2.5">
                    <span className="mr-auto text-[13px] text-danger">Отключить Яндекс?</span>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmYandexDisconnect(false)}>
                      Отмена
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      busy={disconnectYandex.isPending}
                      onClick={() =>
                        disconnectYandex.mutate(undefined, {
                          onSuccess: () => {
                            setConfirmYandexDisconnect(false);
                            show('Яндекс.Календарь отключен', 'success');
                          },
                          onError: () => show('Не удалось отключить', 'error'),
                        })
                      }
                    >
                      Отключить
                    </Button>
                  </div>
                ) : (
                  <Button size="sm" variant="danger" onClick={() => setConfirmYandexDisconnect(true)}>
                    Отключить
                  </Button>
                )}
              </div>
            </>
          ) : (
            <div className="space-y-3 border-t border-hairline px-4 py-3.5">
              <p className="text-[13px] leading-relaxed text-hint">
                Lumi будет видеть занятость из Яндекс.Календаря (только чтение). Нужен{' '}
                <span className="text-ink">пароль приложения</span>: id.yandex.ru → Безопасность →
                Пароли приложений → «Календарь CalDAV».
              </p>
              <label className="block">
                <FieldLabel>Логин Яндекса</FieldLabel>
                <Input value={yandexLogin} onChange={setYandexLogin} placeholder="you@yandex.ru" />
              </label>
              <label className="block">
                <FieldLabel>Пароль приложения</FieldLabel>
                <Input
                  type="password"
                  value={yandexPassword}
                  onChange={setYandexPassword}
                  placeholder="abcdwxyzabcdwxyz"
                />
              </label>
              <Button
                size="sm"
                busy={connectYandex.isPending}
                disabled={yandexLogin.trim().length < 3 || yandexPassword.trim().length < 8}
                onClick={handleYandexConnect}
              >
                Подключить
              </Button>
            </div>
          )}
        </Card>
      </Rise>

      <Rise>
        <p className="mt-2 text-center text-[11.5px] text-hint">
          Lumi {healthQuery.data?.version ?? ''}
        </p>
      </Rise>
    </Stagger>
  );
}
