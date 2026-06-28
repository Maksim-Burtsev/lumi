import { Pencil, Save, Sparkles, StickyNote, Trash2 } from 'lucide-react';
import { Button } from '../ui/Button';
import { Textarea } from '../ui/Field';
import { useAppLocale } from '../../lib/useAppLocale';
import { pickLocaleText } from '../../lib/i18n';

export const PRIVATE_NOTE_SUMMARY_THRESHOLD_CHARS = 600;
export const PRIVATE_NOTE_MAX_CHARS = 4000;

export interface PrivateNoteTarget {
  id: string;
  private_note?: string | null;
  private_note_summary?: string | null;
  private_note_summary_status?: 'pending' | 'ready' | 'failed' | 'not_needed' | null;
}

function normalizedPrivateNoteLength(value: string): number {
  return value.replace(/\s+/g, ' ').trim().length;
}

function truncatePrivateNote(value: string, limit = 560): string {
  const normalized = value.replace(/\s+/g, ' ').trim();
  return normalized.length > limit ? `${normalized.slice(0, limit).trimEnd()}...` : normalized;
}

function stripSummaryPrefix(value: string): string {
  return value.replace(/^\s*(?:ai\s+summary|summary|резюме)\s*[:—-]\s*/i, '').trim();
}

export function PrivateNoteSection({
  event,
  editing,
  expanded,
  draft,
  error,
  saving,
  deleting,
  onEdit,
  onCancel,
  onDelete,
  onDraftChange,
  onExpandedChange,
  onSave,
}: {
  event: PrivateNoteTarget;
  editing: boolean;
  expanded: boolean;
  draft: string;
  error: string | null;
  saving: boolean;
  deleting: boolean;
  onEdit: () => void;
  onCancel: () => void;
  onDelete: () => void;
  onDraftChange: (value: string) => void;
  onExpandedChange: (value: boolean) => void;
  onSave: () => void;
}) {
  const locale = useAppLocale();
  const copy = pickLocaleText(locale, {
    en: {
      label: 'Personal note',
      edit: 'Edit personal note',
      delete: 'Delete personal note',
      placeholder: 'Context just for yourself',
      cancel: 'Cancel',
      save: 'Save',
      expand: 'Show full note',
      collapse: 'Collapse',
      pending: 'Summary is updating',
      failed: 'Summary failed to update',
      add: 'Add note',
      summary: 'AI summary',
    },
    ru: {
      label: 'Личная заметка',
      edit: 'Редактировать личную заметку',
      delete: 'Удалить личную заметку',
      placeholder: 'Короткий личный контекст',
      cancel: 'Отмена',
      save: 'Сохранить',
      expand: 'Показать полностью',
      collapse: 'Свернуть',
      pending: 'Резюме обновляется',
      failed: 'Резюме не обновилось',
      add: 'Добавить заметку',
      summary: 'AI-резюме',
    },
  });
  const note = event.private_note ?? '';
  const hasNote = note.trim().length > 0;
  const isLong = normalizedPrivateNoteLength(note) >= PRIVATE_NOTE_SUMMARY_THRESHOLD_CHARS;
  const hasReadySummary = Boolean(event.private_note_summary_status === 'ready' && event.private_note_summary);
  const showSummary = hasNote && isLong && hasReadySummary && !expanded;
  const showPreview = hasNote && isLong && !hasReadySummary && !expanded;
  const body = showSummary ? stripSummaryPrefix(event.private_note_summary!) : showPreview ? truncatePrivateNote(note) : note;
  const canExpand = hasNote && isLong;

  return (
    <section className="space-y-3 rounded-xl bg-[var(--secondary-bg)] px-3.5 py-3">
      <div className="flex items-center gap-2">
        <StickyNote size={15} className="shrink-0 text-hint" />
        <p className="min-w-0 flex-1 text-[13px] font-medium text-hint">{copy.label}</p>
        {!editing && hasNote && (
          <div className="flex shrink-0 gap-1.5">
            <button
              type="button"
              aria-label={copy.edit}
              onClick={onEdit}
              className="flex h-8 w-8 items-center justify-center rounded-full text-hint transition active:bg-[var(--surface-strong)]"
            >
              <Pencil size={14} />
            </button>
            <button
              type="button"
              aria-label={copy.delete}
              onClick={onDelete}
              disabled={deleting}
              className="flex h-8 w-8 items-center justify-center rounded-full text-danger transition active:bg-[var(--danger-soft)] disabled:opacity-50"
            >
              <Trash2 size={14} />
            </button>
          </div>
        )}
      </div>

      {editing ? (
        <div className="space-y-3">
          <Textarea value={draft} onChange={onDraftChange} rows={5} placeholder={copy.placeholder} />
          <div className="flex items-center justify-between gap-3">
            <span className={`text-[12px] ${draft.length > PRIVATE_NOTE_MAX_CHARS ? 'text-danger' : 'text-hint'}`}>
              {draft.length}/{PRIVATE_NOTE_MAX_CHARS}
            </span>
            <div className="flex shrink-0 gap-2">
              <Button variant="ghost" size="sm" onClick={onCancel}>
                {copy.cancel}
              </Button>
              <Button size="sm" icon={<Save size={14} />} busy={saving} onClick={onSave}>
                {copy.save}
              </Button>
            </div>
          </div>
          {error && <p className="text-[13px] text-danger">{error}</p>}
        </div>
      ) : hasNote ? (
        <div className="space-y-2">
          {showSummary && (
            <div className="inline-flex items-center gap-1.5 rounded-full border border-[var(--accent-border)] bg-[var(--accent-soft)] px-2.5 py-1 text-[11px] font-medium text-accent-text">
              <Sparkles size={12} aria-hidden="true" />
              <span>{copy.summary}</span>
            </div>
          )}
          <p className="whitespace-pre-wrap text-[14px] leading-relaxed text-ink">{body}</p>
          {canExpand && (
            <button
              type="button"
              onClick={() => onExpandedChange(!expanded)}
              className="text-[13px] font-medium text-accent-text"
            >
              {expanded ? copy.collapse : copy.expand}
            </button>
          )}
          {event.private_note_summary_status === 'pending' && (
            <p className="text-[12px] text-hint">{copy.pending}</p>
          )}
          {event.private_note_summary_status === 'failed' && (
            <p className="text-[12px] text-hint">{copy.failed}</p>
          )}
        </div>
      ) : (
        <button
          type="button"
          onClick={onEdit}
          className="flex min-h-10 w-full items-center justify-center rounded-xl border border-dashed border-hairline text-[13.5px] font-medium text-accent-text"
        >
          {copy.add}
        </button>
      )}
    </section>
  );
}
