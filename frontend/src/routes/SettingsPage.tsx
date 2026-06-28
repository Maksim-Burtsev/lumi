import { useEffect, useState } from 'react';
import { Check, Minus } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import { ApiError, api } from '../api/client';
import { openExternalLink } from '../telegram/webapp';
import { qk, useConnectYandex, useDisconnectGoogle, useDisconnectYandex, useHealth, usePatchSettings, useRunPoller, useSettings } from '../api/hooks';
import type { GoogleStatus, ThemeMode, TimeFormat } from '../api/types';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { ErrorState } from '../components/ui/ErrorState';
import { FieldLabel, Input, Select } from '../components/ui/Field';
import { TimeFormatControl } from '../components/settings/TimeFormatControl';
import { TimezonePicker } from '../components/settings/TimezonePicker';
import { SectionHeader } from '../components/ui/SectionHeader';
import { SkeletonList } from '../components/ui/Skeleton';
import { useToast } from '../components/ui/Toast';
import { Rise, Stagger } from '../components/ui/motion';
import { formatRelative, normalizeTimeFormat } from '../lib/format';
import { normalizeAppLocale } from '../lib/i18n';
import { normalizeThemeMode } from '../lib/theme';
import { setThemeMode } from '../telegram/webapp';

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

const STATUS_CLASSES: Record<GoogleStatus['status'], string> = {
  connected: 'bg-[var(--success-soft)] text-success',
  disconnected: 'bg-[var(--secondary-bg)] text-hint',
  error: 'bg-[var(--danger-soft)] text-danger',
  needs_reauth: 'bg-[var(--danger-soft)] text-danger',
};

const LANGUAGE_OPTIONS = [
  { value: 'en', label: 'English' },
  { value: 'ru', label: 'Русский' },
];

const COPY = {
  en: {
    appearance: 'Appearance',
    theme: 'Theme',
    themeTelegram: 'Use Telegram theme',
    themeLight: 'Light',
    themeDark: 'Dark',
    themeSaved: 'Theme saved',
    themeSaveFailed: 'Could not save theme',
    loadError: 'Could not load settings.',
    timezone: 'Time zone',
    timeFormat: 'Time format',
    regionalSettings: 'Regional settings',
    appLanguage: 'App language',
    botReplies: 'Bot replies',
    replyAuto: 'Auto: match each message',
    replyAppLocale: 'Use app language',
    languageSaved: 'Language saved',
    languageSaveFailed: 'Could not save language',
    replyLanguageSaved: 'Reply language saved',
    replyLanguageSaveFailed: 'Could not save reply language',
    timezoneSaved: 'Time zone saved',
    timeFormatSaved: 'Time format saved',
    saveFailed: 'Could not save',
    calendarSynced: 'Calendar synced; events are already in the schedule',
    calendarSyncFailed: 'Sync failed; try the Calendar page button',
    googleConnected: 'Google connected; syncing calendar',
    googleStartFailed: 'Could not start connection',
    googleSecretMissing: 'Put client_secret.json into data/secrets first',
    publicUrlMissing: 'APP_PUBLIC_URL is required (HTTPS tunnel)',
    status: 'Status',
    connected: 'Connected',
    disconnected: 'Disconnected',
    error: 'Error',
    needsReauth: 'Reconnect required',
    lastSync: 'Last sync',
    googleInfo: 'Lumi will get read-only mail access and calendar access. One tap opens Google; allow access and return here.',
    waitingGoogle: 'Waiting for Google confirmation; status updates automatically.',
    connectGoogle: 'Connect Google',
    disconnectGoogle: 'Disconnect Google?',
    googleDisconnected: 'Google disconnected',
    googleDisconnectFailed: 'Could not disconnect',
    cancel: 'Cancel',
    disconnect: 'Disconnect',
    yandexTitle: 'Yandex Calendar',
    account: 'Account',
    access: 'Access',
    readOnlyCalDav: 'read-only (CalDAV)',
    yandexInfo: 'Lumi will see your Yandex Calendar availability (read-only). Use an app password from Yandex ID security settings.',
    yandexLogin: 'Yandex login',
    appPassword: 'App password',
    connect: 'Connect',
    yandexConnected: 'Connected; syncing events...',
    yandexRejected: 'Yandex rejected the login or app password',
    disconnectYandex: 'Disconnect Yandex?',
    yandexDisconnected: 'Yandex Calendar disconnected',
    userFallback: 'User',
  },
  ru: {
    appearance: 'Внешний вид',
    theme: 'Тема',
    themeTelegram: 'Как в Telegram',
    themeLight: 'Светлая',
    themeDark: 'Тёмная',
    themeSaved: 'Тема сохранена',
    themeSaveFailed: 'Не удалось сохранить тему',
    loadError: 'Не удалось загрузить настройки.',
    timezone: 'Часовой пояс',
    timeFormat: 'Формат времени',
    regionalSettings: 'Региональные настройки',
    appLanguage: 'Язык приложения',
    botReplies: 'Ответы бота',
    replyAuto: 'Авто: язык каждого сообщения',
    replyAppLocale: 'Язык приложения',
    languageSaved: 'Язык сохранен',
    languageSaveFailed: 'Не удалось сохранить язык',
    replyLanguageSaved: 'Язык ответов сохранен',
    replyLanguageSaveFailed: 'Не удалось сохранить язык ответов',
    timezoneSaved: 'Часовой пояс сохранён',
    timeFormatSaved: 'Формат времени сохранён',
    saveFailed: 'Не удалось сохранить',
    calendarSynced: 'Календарь синхронизирован — события уже в расписании',
    calendarSyncFailed: 'Синхронизация не удалась — попробуй кнопку на странице Календарь',
    googleConnected: 'Google подключен — синхронизирую календарь',
    googleStartFailed: 'Не удалось начать подключение',
    googleSecretMissing: 'Сначала положи client_secret.json в data/secrets (см. доку)',
    publicUrlMissing: 'Нужен APP_PUBLIC_URL (HTTPS-туннель)',
    status: 'Статус',
    connected: 'Подключен',
    disconnected: 'Не подключен',
    error: 'Ошибка',
    needsReauth: 'Нужна повторная авторизация',
    lastSync: 'Последняя синхронизация',
    googleInfo: 'Lumi получит доступ к почте (только чтение) и календарю. Один тап — откроется Google, разреши доступ и вернись сюда.',
    waitingGoogle: 'Жду подтверждения в Google… статус обновится сам.',
    connectGoogle: 'Подключить Google',
    disconnectGoogle: 'Отключить Google?',
    googleDisconnected: 'Google отключен',
    googleDisconnectFailed: 'Не удалось отключить',
    cancel: 'Отмена',
    disconnect: 'Отключить',
    yandexTitle: 'Яндекс.Календарь',
    account: 'Аккаунт',
    access: 'Доступ',
    readOnlyCalDav: 'только чтение (CalDAV)',
    yandexInfo: 'Lumi будет видеть занятость из Яндекс.Календаря (только чтение). Нужен пароль приложения: id.yandex.ru → Безопасность → Пароли приложений → «Календарь CalDAV».',
    yandexLogin: 'Логин Яндекса',
    appPassword: 'Пароль приложения',
    connect: 'Подключить',
    yandexConnected: 'Подключено! Синхронизирую события…',
    yandexRejected: 'Яндекс отклонил логин или пароль приложения',
    disconnectYandex: 'Отключить Яндекс?',
    yandexDisconnected: 'Яндекс.Календарь отключен',
    userFallback: 'Пользователь',
  },
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
  const yandexSyncPoller = useRunPoller(yandexSyncRunId, [qk.eventsAll, qk.settings, qk.today]);
  const queryClientForGoogle = useQueryClient();
  const locale = normalizeAppLocale(settingsQuery.data?.user.locale);
  const copy = COPY[locale];

  useEffect(() => {
    if (yandexSyncRunId === null) return;
    if (yandexSyncPoller.status === 'completed') {
      show(copy.calendarSynced, 'success');
      setYandexSyncRunId(null);
    } else if (yandexSyncPoller.status === 'failed' || yandexSyncPoller.status === 'timeout') {
      show(copy.calendarSyncFailed, 'error');
      setYandexSyncRunId(null);
    }
  }, [copy.calendarSyncFailed, copy.calendarSynced, yandexSyncPoller.status, yandexSyncRunId, show]);

  useEffect(() => {
    if (!googleConnecting) return;
    if (settingsQuery.data?.google.status === 'connected') {
      setGoogleConnecting(false);
      show(copy.googleConnected, 'success');
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
  }, [copy.googleConnected, googleConnecting, settingsQuery.data?.google.status]);

  if (settingsQuery.isPending) return <SkeletonList count={4} lines={3} />;
  if (settingsQuery.isError) {
    return <ErrorState message={copy.loadError} onRetry={() => void settingsQuery.refetch()} />;
  }

  const { user, google, yandex } = settingsQuery.data;
  const displayName = [user.first_name, user.last_name].filter(Boolean).join(' ') || user.username || copy.userFallback;
  const initial = (user.first_name ?? user.username ?? 'L').slice(0, 1).toUpperCase();
  const statusLabels: Record<GoogleStatus['status'], string> = {
    connected: copy.connected,
    disconnected: copy.disconnected,
    error: copy.error,
    needs_reauth: copy.needsReauth,
  };
  const googleStatus = { label: statusLabels[google.status], className: STATUS_CLASSES[google.status] };
  const yandexStatus = { label: statusLabels[yandex.status], className: STATUS_CLASSES[yandex.status] };
  const yandexConnected = yandex.status === 'connected' || yandex.status === 'needs_reauth';
  const replyLanguageMode = typeof user.settings.reply_language_mode === 'string'
    ? user.settings.reply_language_mode
    : 'auto';
  const timeFormat = normalizeTimeFormat(user.settings.time_format);
  const themeMode = normalizeThemeMode(user.settings.theme_mode);
  const timeDisplay = { locale, timeFormat, timezone: user.timezone };

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
            ? copy.googleSecretMissing
            : code === 'public_url_missing'
              ? copy.publicUrlMissing
              : copy.googleStartFailed,
          'error',
        );
      });
  };

  const handleYandexConnect = () => {
    connectYandex.mutate(
      { username: yandexLogin.trim(), app_password: yandexPassword.trim() },
      {
        onSuccess: (data) => {
          setYandexLogin('');
          setYandexPassword('');
          show(copy.yandexConnected, 'success');
          if (data.run_id) setYandexSyncRunId(data.run_id);
        },
        onError: () => show(copy.yandexRejected, 'error'),
      },
    );
  };

  const handleLocale = (locale: string) => {
    const targetCopy = COPY[normalizeAppLocale(locale)];
    patchSettings.mutate(
      { locale },
      {
        onSuccess: () => show(targetCopy.languageSaved, 'success'),
        onError: () => show(targetCopy.languageSaveFailed, 'error'),
      },
    );
  };

  const handleReplyLanguageMode = (reply_language_mode: string) => {
    patchSettings.mutate(
      { reply_language_mode: reply_language_mode as 'auto' | 'app_locale' },
      {
        onSuccess: () => show(copy.replyLanguageSaved, 'success'),
        onError: () => show(copy.replyLanguageSaveFailed, 'error'),
      },
    );
  };

  const handleTimezone = (timezone: string) => {
    patchSettings.mutate(
      { timezone },
      {
        onSuccess: () => show(copy.timezoneSaved, 'success'),
        onError: () => show(copy.saveFailed, 'error'),
      },
    );
  };

  const handleTimeFormat = (time_format: TimeFormat) => {
    patchSettings.mutate(
      { time_format },
      {
        onSuccess: () => show(copy.timeFormatSaved, 'success'),
        onError: () => show(copy.saveFailed, 'error'),
      },
    );
  };

  const handleThemeMode = (theme_mode: ThemeMode) => {
    const previous = themeMode;
    setThemeMode(theme_mode);
    patchSettings.mutate(
      { theme_mode },
      {
        onSuccess: () => show(copy.themeSaved, 'success'),
        onError: () => {
          setThemeMode(previous);
          show(copy.themeSaveFailed, 'error');
        },
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
            <FieldLabel>{copy.botReplies}</FieldLabel>
            <Select
              value={replyLanguageMode}
              ariaLabel={copy.botReplies}
              onChange={handleReplyLanguageMode}
              options={[
                { value: 'auto', label: copy.replyAuto },
                { value: 'app_locale', label: copy.replyAppLocale },
              ]}
            />
          </label>
        </Card>
      </Rise>

      {/* Appearance */}
      <Rise>
        <SectionHeader title={copy.appearance} />
        <Card className="card-strong !p-0 overflow-hidden">
          <label className="flex min-h-[68px] items-center justify-between gap-3 px-4 py-3">
            <span className="min-w-0 text-[13.5px] font-medium text-ink">{copy.theme}</span>
            <span className="w-[178px] shrink-0">
              <Select
                value={themeMode}
                ariaLabel={copy.theme}
                onChange={(value) => handleThemeMode(normalizeThemeMode(value))}
                options={[
                  { value: 'telegram', label: copy.themeTelegram },
                  { value: 'light', label: copy.themeLight },
                  { value: 'dark', label: copy.themeDark },
                ]}
              />
            </span>
          </label>
        </Card>
      </Rise>

      {/* Regional settings */}
      <Rise>
        <SectionHeader title={copy.regionalSettings} />
        <Card className="card-strong !p-0 overflow-hidden">
          <TimezonePicker
            value={user.timezone}
            onChange={handleTimezone}
            locale={locale}
          />
          <div className="border-t border-hairline">
            <TimeFormatControl
              value={timeFormat}
              onChange={handleTimeFormat}
              locale={locale}
              timezone={user.timezone}
            />
          </div>
          <label className="flex min-h-[68px] items-center justify-between gap-3 border-t border-hairline px-4 py-3">
            <span className="min-w-0 text-[13.5px] font-medium text-ink">{copy.appLanguage}</span>
            <span className="w-[132px] shrink-0">
              <Select
                value={user.locale || 'en'}
                ariaLabel={copy.appLanguage}
                onChange={handleLocale}
                options={LANGUAGE_OPTIONS}
              />
            </span>
          </label>
        </Card>
      </Rise>

      {/* Google */}
      <Rise>
        <SectionHeader title="Google" />
        <Card className="card-strong !p-0">
          <div className="flex min-h-[48px] items-center justify-between gap-3 px-4 py-2.5">
            <span className="text-[13.5px] text-ink">{copy.status}</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-medium ${googleStatus.className}`}>
              {googleStatus.label}
            </span>
          </div>
          <div className="divide-y divide-[var(--hairline)] border-t border-hairline">
            <BoolRow label="Gmail" value={google.gmail_available} />
            <BoolRow label="Calendar" value={google.calendar_available} />
            <InfoRow
              label={copy.lastSync}
              value={google.last_sync_at ? formatRelative(google.last_sync_at, timeDisplay) : '—'}
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
                  <span className="mr-auto text-[13px] text-danger">{copy.disconnectGoogle}</span>
                  <Button size="sm" variant="ghost" onClick={() => setConfirmDisconnect(false)}>
                    {copy.cancel}
                  </Button>
                  <Button
                    size="sm"
                    variant="danger"
                    busy={disconnectGoogle.isPending}
                    onClick={() =>
                      disconnectGoogle.mutate(undefined, {
                        onSuccess: () => {
                          setConfirmDisconnect(false);
                          show(copy.googleDisconnected, 'success');
                        },
                        onError: () => show(copy.googleDisconnectFailed, 'error'),
                      })
                    }
                  >
                    {copy.disconnect}
                  </Button>
                </div>
              ) : (
                <Button size="sm" variant="danger" onClick={() => setConfirmDisconnect(true)}>
                  {copy.disconnect}
                </Button>
              )
            ) : (
              <div>
                <p className="text-[13px] leading-relaxed text-hint">
                  {copy.googleInfo}
                </p>
                <Button
                  className="mt-3"
                  busy={googleConnecting}
                  onClick={handleGoogleConnect}
                >
                  {copy.connectGoogle}
                </Button>
                {googleConnecting && (
                  <p className="mt-2 text-[12.5px] text-hint">
                    {copy.waitingGoogle}
                  </p>
                )}
              </div>
            )}
          </div>
        </Card>
      </Rise>

      {/* Yandex Calendar */}
      <Rise>
        <SectionHeader title={copy.yandexTitle} />
        <Card className="card-strong !p-0">
          <div className="flex min-h-[48px] items-center justify-between gap-3 px-4 py-2.5">
            <span className="text-[13.5px] text-ink">{copy.status}</span>
            <span className={`rounded-full px-2.5 py-0.5 text-[11.5px] font-medium ${yandexStatus.className}`}>
              {yandexStatus.label}
            </span>
          </div>
          {yandexConnected ? (
            <>
              <div className="divide-y divide-[var(--hairline)] border-t border-hairline">
                <InfoRow label={copy.account} value={yandex.username ?? '—'} />
                <InfoRow
                  label={copy.lastSync}
                  value={yandex.last_sync_at ? formatRelative(yandex.last_sync_at, timeDisplay) : '—'}
                />
                <InfoRow label={copy.access} value={copy.readOnlyCalDav} />
              </div>
              {yandex.last_error && (
                <p className="border-t border-hairline px-4 py-3 text-[12.5px] leading-snug text-danger">
                  {yandex.last_error}
                </p>
              )}
              <div className="border-t border-hairline px-4 py-3.5">
                {confirmYandexDisconnect ? (
                  <div className="flex items-center gap-2.5">
                    <span className="mr-auto text-[13px] text-danger">{copy.disconnectYandex}</span>
                    <Button size="sm" variant="ghost" onClick={() => setConfirmYandexDisconnect(false)}>
                      {copy.cancel}
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      busy={disconnectYandex.isPending}
                      onClick={() =>
                        disconnectYandex.mutate(undefined, {
                          onSuccess: () => {
                            setConfirmYandexDisconnect(false);
                            show(copy.yandexDisconnected, 'success');
                          },
                          onError: () => show(copy.googleDisconnectFailed, 'error'),
                        })
                      }
                    >
                      {copy.disconnect}
                    </Button>
                  </div>
                ) : (
                  <Button size="sm" variant="danger" onClick={() => setConfirmYandexDisconnect(true)}>
                    {copy.disconnect}
                  </Button>
                )}
              </div>
            </>
          ) : (
            <div className="space-y-3 border-t border-hairline px-4 py-3.5">
              <p className="text-[13px] leading-relaxed text-hint">
                {copy.yandexInfo}
              </p>
              <label className="block">
                <FieldLabel>{copy.yandexLogin}</FieldLabel>
                <Input value={yandexLogin} onChange={setYandexLogin} placeholder="you@yandex.ru" />
              </label>
              <label className="block">
                <FieldLabel>{copy.appPassword}</FieldLabel>
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
                {copy.connect}
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
