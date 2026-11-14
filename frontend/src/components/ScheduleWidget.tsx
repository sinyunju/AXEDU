// 메인 화면 일정: 슈퍼스쿨 학사 일정 + 토끼와 거북이 수업. 주/월 보기를 고를 수 있음
import { ArrowLeft, ArrowRight, CalendarDays, CalendarRange, ChevronRight, Clock, School } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../api';
import { OPEN_TO_STUDENTS, type CalendarEvent, type Role } from '../api/types';
import { useAsync } from '../hooks/useAsync';
import { Segmented } from './Segmented';
import { SuperschoolButton } from './SuperschoolButton';

type View = 'week' | 'month';
const WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일'];
const VIEW_KEY = 'pref.calendarView';

// ---------- 날짜 계산 ----------

function startOfDay(d: Date) {
  const x = new Date(d);
  x.setHours(0, 0, 0, 0);
  return x;
}
function addDays(d: Date, n: number) {
  const x = new Date(d);
  x.setDate(x.getDate() + n);
  return x;
}
/** 그 주 월요일 */
function startOfWeek(d: Date) {
  const x = startOfDay(d);
  return addDays(x, -((x.getDay() + 6) % 7));
}
const sameDay = (a: Date, b: Date) => startOfDay(a).getTime() === startOfDay(b).getTime();

/** 이 일정이 그 날짜에 걸쳐 있는지 (여러 날 일정 포함) */
function covers(e: CalendarEvent, day: Date) {
  const s = startOfDay(new Date(e.start)).getTime();
  const end = startOfDay(new Date(e.end ?? e.start)).getTime();
  const t = startOfDay(day).getTime();
  return t >= s && t <= end;
}

/** 보기 범위: 주 보기는 그 주 7일, 월 보기는 그 달을 덮는 월~일 주들 */
function rangeFor(view: View, anchor: Date) {
  if (view === 'week') {
    const start = startOfWeek(anchor);
    return { start, days: 7 };
  }
  const first = new Date(anchor.getFullYear(), anchor.getMonth(), 1);
  const last = new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0);
  const start = startOfWeek(first);
  const end = addDays(startOfWeek(last), 7);
  return { start, days: Math.round((end.getTime() - start.getTime()) / 86_400_000) };
}

const fmtTime = (iso: string) => new Date(iso).toLocaleTimeString('ko-KR', { hour: 'numeric', minute: '2-digit' });
const fmtDay = (d: Date) => d.toLocaleDateString('ko-KR', { month: 'long', day: 'numeric', weekday: 'short' });

// ---------- 일정 종류 ----------

const TONES = [
  { key: 'lesson', label: '수업' },
  { key: 'exam', label: '시험' },
  { key: 'event', label: '학교 행사' },
  { key: 'off', label: '휴업일' },
] as const;

function tone(e: CalendarEvent) {
  if (e.source === 'lesson') return 'lesson';
  if (e.category === '시험') return 'exam';
  if (e.category === '휴업일') return 'off';
  return 'event';
}

function whenLabel(e: CalendarEvent) {
  if (!e.allDay) return fmtTime(e.start);
  if (e.end && !sameDay(new Date(e.start), new Date(e.end))) {
    const s = new Date(e.start);
    const t = new Date(e.end);
    return `${s.getMonth() + 1}/${s.getDate()} ~ ${t.getMonth() + 1}/${t.getDate()}`;
  }
  return '하루 종일';
}

// ---------- 컴포넌트 ----------

export function ScheduleWidget({ role }: { role: Role }) {
  const today = useMemo(() => startOfDay(new Date()), []);
  const [view, setViewState] = useState<View>(() => {
    try {
      return localStorage.getItem(VIEW_KEY) === 'week' ? 'week' : 'month';
    } catch {
      return 'month';
    }
  });
  const [anchor, setAnchor] = useState(today); // 보고 있는 주/달 안의 아무 날
  const [selected, setSelected] = useState(today);

  const { start, days } = rangeFor(view, anchor);
  const from = start.toISOString();
  const to = addDays(start, days).toISOString();
  const cal = useAsync(() => api.getCalendar(from, to), [from, to]);

  const upFrom = today.toISOString();
  const upTo = addDays(today, 15).toISOString();
  const upcoming = useAsync(() => api.getCalendar(upFrom, upTo), [upFrom, upTo]);

  const events = cal.data?.events ?? [];
  const cells = Array.from({ length: days }, (_, i) => addDays(start, i));
  const dayEvents = events.filter((e) => covers(e, selected));
  const upcomingEvents = (upcoming.data?.events ?? []).filter((e) => !covers(e, today) || e.source === 'lesson');

  function setView(v: View) {
    setViewState(v);
    setAnchor(selected);
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* 무시 */
    }
  }

  function move(n: number) {
    const next =
      view === 'week' ? addDays(anchor, n * 7) : new Date(anchor.getFullYear(), anchor.getMonth() + n, 1);
    setAnchor(next);
    setSelected(view === 'week' ? startOfWeek(next) : next);
  }

  function goToday() {
    setAnchor(today);
    setSelected(today);
  }

  function lessonLink(e: CalendarEvent) {
    if (!e.lessonId) return null;
    if (role === 'teacher') return `/teacher/lessons/${e.lessonId}/review`;
    return e.lessonStatus && OPEN_TO_STUDENTS.includes(e.lessonStatus) ? `/class/${e.lessonId}` : null;
  }

  const title =
    view === 'month'
      ? `${anchor.getFullYear()}년 ${anchor.getMonth() + 1}월`
      : `${start.getMonth() + 1}월 ${start.getDate()}일 – ${addDays(start, 6).getMonth() + 1}월 ${addDays(start, 6).getDate()}일`;
  const maxChips = view === 'month' ? 2 : 5;

  return (
    <div className="stack">
      <section className="card cal-card">
        <div className="cal-head">
          <h2 className="cal-title">{title}</h2>
          <div className="row">
            <Segmented
              ariaLabel="보기 방식"
              kind="radio"
              size="sm"
              options={[
                { value: 'week', label: '주', icon: CalendarRange },
                { value: 'month', label: '월', icon: CalendarDays },
              ]}
              value={view}
              onChange={setView}
            />
            <div className="row" style={{ gap: 4 }}>
              <button className="btn btn-icon btn-sm" aria-label={view === 'week' ? '지난주' : '지난달'} onClick={() => move(-1)}>
                <ArrowLeft size={16} />
              </button>
              <button className="btn btn-sm" onClick={goToday}>
                오늘
              </button>
              <button className="btn btn-icon btn-sm" aria-label={view === 'week' ? '다음 주' : '다음 달'} onClick={() => move(1)}>
                <ArrowRight size={16} />
              </button>
            </div>
          </div>
        </div>

        <div className={`cal-grid ${view}`} role="grid" aria-label={title}>
          {WEEKDAYS.map((w, i) => (
            <div key={w} className={`cal-dow ${i === 6 ? 'sun' : ''}`} role="columnheader">
              {w}
            </div>
          ))}
          {cells.map((d) => {
            const evs = events.filter((e) => covers(e, d));
            const outside = view === 'month' && d.getMonth() !== anchor.getMonth();
            const cls = [
              'cal-cell',
              sameDay(d, selected) ? 'selected' : '',
              sameDay(d, today) ? 'today' : '',
              outside ? 'outside' : '',
              d.getDay() === 0 ? 'sun' : '',
            ].join(' ');
            return (
              <button
                key={d.toISOString()}
                role="gridcell"
                aria-selected={sameDay(d, selected)}
                aria-label={`${fmtDay(d)}, 일정 ${evs.length}개`}
                className={cls}
                onClick={() => setSelected(d)}
              >
                <span className="cal-num">{d.getDate()}</span>
                <span className="cal-chips">
                  {evs.slice(0, maxChips).map((e) => (
                    <span key={e.id} className={`ev-chip ${tone(e)}`}>
                      <i />
                      <span className="ev-text">
                        <span className="ev-title">{e.title}</span>
                        {!e.allDay && <span className="ev-time">{fmtTime(e.start)}</span>}
                      </span>
                    </span>
                  ))}
                  {evs.length > maxChips && <span className="ev-more">+{evs.length - maxChips}</span>}
                </span>
              </button>
            );
          })}
        </div>

        <div className="cal-legend">
          {TONES.map((t) => (
            <span key={t.key}>
              <i className={`dot ${t.key}`} /> {t.label}
            </span>
          ))}
        </div>

        {cal.data && !cal.data.superschoolLinked && (
          <div className="link-banner">
            <School size={20} />
            <span className="grow small">
              슈퍼스쿨 계정을 연결하면 시험·행사 같은 <strong>학사 일정</strong>도 함께 볼 수 있어요.
            </span>
            <SuperschoolButton mode="link" returnTo={role === 'teacher' ? '/teacher' : '/student'} className="btn-sm" />
          </div>
        )}
      </section>

      <section className="card stack">
        <div>
          <h3 className="list-head">{fmtDay(selected)}</h3>
          {dayEvents.length === 0 ? (
            <div className="empty-box">일정이 없어요</div>
          ) : (
            <EventList events={dayEvents} linkOf={lessonLink} />
          )}
        </div>
        <div>
          <h3 className="list-head">
            다가오는 일정 <span className="muted small">(14일)</span>
          </h3>
          {upcoming.loading ? (
            <p className="muted small">불러오는 중…</p>
          ) : upcomingEvents.length === 0 ? (
            <div className="empty-box">2주 안에 일정이 없어요</div>
          ) : (
            <EventList events={upcomingEvents.slice(0, 6)} linkOf={lessonLink} showDate />
          )}
        </div>
      </section>
    </div>
  );
}

function EventList({
  events,
  linkOf,
  showDate = false,
}: {
  events: CalendarEvent[];
  linkOf: (e: CalendarEvent) => string | null;
  showDate?: boolean;
}) {
  return (
    <ul className="event-list">
      {events.map((e) => {
        const link = linkOf(e);
        const body = (
          <>
            <i className={`dot ${tone(e)}`} style={{ marginTop: 7 }} />
            <div className="grow">
              <strong>{e.title}</strong>
              <div className="lesson-meta">
                <span className="row" style={{ gap: 4 }}>
                  <Clock size={13} />
                  {showDate && `${fmtDay(new Date(e.start))} · `}
                  {whenLabel(e)}
                </span>
                {e.source === 'superschool' ? (
                  <span className="chip" style={{ height: 24 }}>
                    <School size={12} /> 학사 일정
                  </span>
                ) : (
                  <span className="chip chip-blue" style={{ height: 24 }}>
                    {e.courseName ?? '수업'}
                  </span>
                )}
              </div>
            </div>
            {link && <ChevronRight size={18} style={{ color: 'var(--primary-text)', alignSelf: 'center' }} />}
          </>
        );
        return (
          <li key={e.id}>
            {link ? (
              <Link to={link} className="event-row link">
                {body}
              </Link>
            ) : (
              <div className="event-row">{body}</div>
            )}
          </li>
        );
      })}
    </ul>
  );
}
