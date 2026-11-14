// 수업 자료(PDF 페이지 이미지) + 필기 + 레이저 포인터. 교사·학생 공용.
// - 좌표·굵기는 페이지 크기 기준 0~1 비율로 저장 → 화면 크기·전체화면이 바뀌어도 같은 자리에 그려짐
// - 펜(애플펜슬)을 한 번이라도 쓰면 손바닥 터치는 그리기에서 무시 (팜 리젝션)
// - fill: 부모 높이를 꽉 채움 (전체화면). 아니면 너비에 맞추되 화면 높이를 넘지 않음
import { Crosshair, Eraser, Highlighter, MousePointer2, PenLine, Trash2, Undo2 } from 'lucide-react';
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import type { PointerPos, Stroke } from '../api/types';

export type Tool = 'view' | 'pen' | 'highlighter' | 'eraser' | 'laser';

const PEN_COLORS = ['#121a35', '#e5484d', '#2f5ee8', '#109f6a'];
const HIGHLIGHT_COLORS = ['#ffd60a', '#7ee081', '#ff8fc7', '#7cc4ff'];
const WIDTH = { pen: 0.0035, highlighter: 0.022 };
const HIGHLIGHT_ALPHA = 0.38;
const ERASER_RADIUS_PX = 14;
const POINTER_SEND_MS = 40; // 레이저 위치 전송 간격 (초당 25번)
const HISTORY_LIMIT = 50;

interface Props {
  pageKey: number; // 페이지가 바뀌면 되돌리기 기록을 따로 둠
  imageUrl?: string;
  fallback?: ReactNode; // 이미지가 없을 때 대신 보여 줄 내용
  alt: string;
  strokes: Stroke[];
  onStrokesChange: (strokes: Stroke[]) => void;
  laser?: boolean; // 레이저 도구 사용 가능 (교사)
  onPointer?: (pos: PointerPos) => void;
  remotePointer?: PointerPos; // 선생님 레이저 (학생)
  fill?: boolean;
  toolbarEnd?: ReactNode; // 툴바 오른쪽 끝 (전체화면 버튼, 저장 상태 등)
}

export function SlideBoard({
  pageKey,
  imageUrl,
  fallback,
  alt,
  strokes,
  onStrokesChange,
  laser = false,
  onPointer,
  remotePointer = null,
  fill = false,
  toolbarEnd,
}: Props) {
  const [tool, setTool] = useState<Tool>('view');
  const [penColor, setPenColor] = useState(PEN_COLORS[0]);
  const [hlColor, setHlColor] = useState(HIGHLIGHT_COLORS[0]);
  const [aspect, setAspect] = useState(16 / 9);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [localPointer, setLocalPointer] = useState<PointerPos>(null);

  const stageRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<HTMLDivElement>(null);
  const baseRef = useRef<HTMLCanvasElement>(null);
  const liveRef = useRef<HTMLCanvasElement>(null);
  const drawing = useRef<{ id: number; stroke: Stroke } | null>(null);
  const erasing = useRef<number | null>(null);
  const penSeen = useRef(false);
  const history = useRef(new Map<number, Stroke[][]>());
  const strokesRef = useRef(strokes);
  strokesRef.current = strokes;
  const lastSent = useRef(0);
  const sendTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // ---------- 크기: 페이지 비율을 지키며 무대 안에 꼭 맞춤 ----------
  useLayoutEffect(() => {
    const stage = stageRef.current;
    if (!stage) return;
    const measure = () => {
      const w = stage.clientWidth;
      const maxH = fill ? stage.clientHeight : parseFloat(getComputedStyle(stage).maxHeight) || Infinity;
      let fw = w;
      let fh = fw / aspect;
      if (fh > maxH) {
        fh = maxH;
        fw = fh * aspect;
      }
      const next = { w: Math.floor(fw), h: Math.floor(fh) };
      setSize((prev) => (prev.w === next.w && prev.h === next.h ? prev : next));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(stage);
    window.addEventListener('resize', measure);
    return () => {
      ro.disconnect();
      window.removeEventListener('resize', measure);
    };
  }, [aspect, fill]);

  // ---------- 그리기 ----------
  const redrawBase = useCallback(() => {
    const canvas = baseRef.current;
    if (!canvas || !size.w) return;
    const ctx = prepare(canvas, size.w, size.h);
    strokes.forEach((s) => drawStroke(ctx, s, size.w, size.h));
  }, [strokes, size]);

  useEffect(redrawBase, [redrawBase]);
  useEffect(() => {
    if (liveRef.current && size.w) prepare(liveRef.current, size.w, size.h);
  }, [size]);

  const redrawLive = () => {
    const canvas = liveRef.current;
    if (!canvas || !size.w) return;
    const ctx = canvas.getContext('2d')!;
    ctx.clearRect(0, 0, size.w, size.h);
    if (drawing.current) drawStroke(ctx, drawing.current.stroke, size.w, size.h);
  };

  // ---------- 변경·되돌리기 ----------
  const commit = (next: Stroke[]) => {
    const stack = history.current.get(pageKey) ?? [];
    stack.push(strokesRef.current);
    if (stack.length > HISTORY_LIMIT) stack.shift();
    history.current.set(pageKey, stack);
    strokesRef.current = next;
    onStrokesChange(next);
  };
  const undoStack = history.current.get(pageKey) ?? [];
  const undo = () => {
    const prev = undoStack.pop();
    if (prev) {
      strokesRef.current = prev;
      onStrokesChange(prev);
    }
  };
  const clearAll = () => {
    if (strokes.length && window.confirm('이 페이지 필기를 모두 지울까요?')) commit([]);
  };

  // ---------- 레이저 ----------
  const sendPointer = useCallback(
    (pos: PointerPos, force = false) => {
      if (!onPointer) return;
      clearTimeout(sendTimer.current);
      const wait = POINTER_SEND_MS - (Date.now() - lastSent.current);
      if (force || wait <= 0) {
        lastSent.current = Date.now();
        onPointer(pos);
      } else {
        sendTimer.current = setTimeout(() => {
          lastSent.current = Date.now();
          onPointer(pos);
        }, wait);
      }
    },
    [onPointer],
  );
  const hidePointer = useCallback(() => {
    setLocalPointer(null);
    sendPointer(null, true);
  }, [sendPointer]);

  // 레이저를 내려놓거나 페이지를 넘기면 포인터 숨김
  useEffect(() => {
    if (tool !== 'laser') hidePointer();
  }, [tool, pageKey, hidePointer]);
  useEffect(() => () => clearTimeout(sendTimer.current), []);

  // ---------- 포인터 이벤트 ----------
  const toPos = (e: { clientX: number; clientY: number }): [number, number] => {
    const r = frameRef.current!.getBoundingClientRect();
    return [round((e.clientX - r.left) / r.width), round((e.clientY - r.top) / r.height)];
  };
  const ignoreTouch = (e: React.PointerEvent) => {
    if (e.pointerType === 'pen') penSeen.current = true;
    return e.pointerType === 'touch' && penSeen.current;
  };

  const eraseAt = (x: number, y: number) => {
    const rx = ERASER_RADIUS_PX / size.w;
    const ry = ERASER_RADIUS_PX / size.h;
    const keep = strokesRef.current.filter((s) => !hits(s, x, y, rx, ry, size.w));
    if (keep.length !== strokesRef.current.length) commit(keep);
  };

  const onDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (tool === 'view' || ignoreTouch(e) || (e.pointerType === 'mouse' && e.button !== 0)) return;
    e.preventDefault();
    e.currentTarget.setPointerCapture(e.pointerId);
    const [x, y] = toPos(e);
    if (tool === 'laser') {
      setLocalPointer({ x, y });
      sendPointer({ x, y }, true);
    } else if (tool === 'eraser') {
      erasing.current = e.pointerId;
      eraseAt(x, y);
    } else {
      drawing.current = {
        id: e.pointerId,
        stroke: {
          tool,
          color: tool === 'pen' ? penColor : hlColor,
          width: WIDTH[tool],
          points: [[x, y]],
        },
      };
      redrawLive();
    }
  };

  const onMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (tool === 'view' || ignoreTouch(e)) return;
    if (tool === 'laser') {
      // 마우스는 누르지 않아도 따라다님, 펜·터치는 닿아 있을 때만
      if (e.pointerType !== 'mouse' && e.buttons === 0) return;
      const [x, y] = toPos(e);
      setLocalPointer({ x, y });
      sendPointer({ x, y });
      return;
    }
    if (tool === 'eraser') {
      if (erasing.current === e.pointerId) eraseAt(...toPos(e));
      return;
    }
    const d = drawing.current;
    if (!d || d.id !== e.pointerId) return;
    const events = e.nativeEvent.getCoalescedEvents?.() ?? [e.nativeEvent];
    const pts = d.stroke.points;
    for (const ev of events) {
      const [x, y] = toPos(ev);
      const [px, py] = pts[pts.length - 1];
      if (Math.hypot((x - px) * size.w, (y - py) * size.h) >= 1.5) pts.push([x, y]);
    }
    redrawLive();
  };

  const onUp = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (tool === 'laser') {
      if (e.pointerType !== 'mouse') hidePointer();
      return;
    }
    if (erasing.current === e.pointerId) erasing.current = null;
    const d = drawing.current;
    if (d && d.id === e.pointerId) {
      drawing.current = null;
      commit([...strokesRef.current, d.stroke]);
      redrawLive();
    }
  };

  const onLeave = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (tool === 'laser' && e.pointerType === 'mouse') hidePointer();
  };

  const colors = tool === 'pen' ? PEN_COLORS : tool === 'highlighter' ? HIGHLIGHT_COLORS : null;
  const current = tool === 'pen' ? penColor : hlColor;
  const shownPointer = localPointer ?? remotePointer;

  return (
    <div className={`slide-board ${fill ? 'fill' : ''}`}>
      <div className="slide-toolbar" role="toolbar" aria-label="필기 도구">
        <ToolButton label="보기" active={tool === 'view'} onClick={() => setTool('view')}>
          <MousePointer2 size={18} />
        </ToolButton>
        <ToolButton label="펜" active={tool === 'pen'} onClick={() => setTool('pen')}>
          <PenLine size={18} />
        </ToolButton>
        <ToolButton label="형광펜" active={tool === 'highlighter'} onClick={() => setTool('highlighter')}>
          <Highlighter size={18} />
        </ToolButton>
        <ToolButton label="지우개" active={tool === 'eraser'} onClick={() => setTool('eraser')}>
          <Eraser size={18} />
        </ToolButton>
        {laser && (
          <ToolButton label="레이저 포인터" active={tool === 'laser'} onClick={() => setTool('laser')}>
            <Crosshair size={18} />
          </ToolButton>
        )}
        {colors && (
          <>
            <span className="tool-sep" />
            {colors.map((c) => (
              <button
                key={c}
                className={`tool-color ${c === current ? 'active' : ''}`}
                style={{ background: c }}
                aria-label={`색 ${c}`}
                aria-pressed={c === current}
                onClick={() => (tool === 'pen' ? setPenColor(c) : setHlColor(c))}
              />
            ))}
          </>
        )}
        <span className="tool-sep" />
        <ToolButton label="되돌리기" onClick={undo} disabled={undoStack.length === 0}>
          <Undo2 size={18} />
        </ToolButton>
        <ToolButton label="이 페이지 필기 모두 지우기" onClick={clearAll} disabled={strokes.length === 0}>
          <Trash2 size={18} />
        </ToolButton>
        {toolbarEnd && <span className="tool-end">{toolbarEnd}</span>}
      </div>

      <div className="slide-stage" ref={stageRef}>
        <div
          ref={frameRef}
          className={`slide-frame tool-${tool}`}
          style={size.w ? { width: size.w, height: size.h } : undefined}
        >
          {imageUrl ? (
            <img
              src={imageUrl}
              alt={alt}
              draggable={false}
              onLoad={(e) => {
                const { naturalWidth: w, naturalHeight: h } = e.currentTarget;
                if (w && h) setAspect(w / h);
              }}
            />
          ) : (
            <div className="slide-fallback">{fallback}</div>
          )}
          <canvas ref={baseRef} className="slide-canvas" aria-hidden />
          <canvas
            ref={liveRef}
            className="slide-canvas live"
            aria-hidden
            onPointerDown={onDown}
            onPointerMove={onMove}
            onPointerUp={onUp}
            onPointerCancel={onUp}
            onPointerLeave={onLeave}
          />
          {shownPointer && (
            <span
              className="laser-dot"
              style={{ transform: `translate(${shownPointer.x * size.w}px, ${shownPointer.y * size.h}px)` }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function ToolButton({
  label,
  active,
  disabled,
  onClick,
  children,
}: {
  label: string;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      className={`tool-btn ${active ? 'active' : ''}`}
      title={label}
      aria-label={label}
      aria-pressed={active}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

// ---------- 캔버스 도우미 ----------

const round = (v: number) => Math.round(Math.min(Math.max(v, 0), 1) * 10000) / 10000;

function prepare(canvas: HTMLCanvasElement, w: number, h: number) {
  const dpr = window.devicePixelRatio || 1;
  if (canvas.width !== Math.round(w * dpr) || canvas.height !== Math.round(h * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext('2d')!;
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  return ctx;
}

function drawStroke(ctx: CanvasRenderingContext2D, s: Stroke, w: number, h: number) {
  const lw = Math.max(1, s.width * w);
  ctx.save();
  ctx.globalAlpha = s.tool === 'highlighter' ? HIGHLIGHT_ALPHA : 1;
  ctx.globalCompositeOperation = s.tool === 'highlighter' ? 'multiply' : 'source-over';
  ctx.strokeStyle = s.color;
  ctx.fillStyle = s.color;
  ctx.lineCap = 'round';
  ctx.lineJoin = 'round';
  ctx.lineWidth = lw;
  const pts = s.points;
  if (pts.length === 1) {
    ctx.beginPath();
    ctx.arc(pts[0][0] * w, pts[0][1] * h, lw / 2, 0, Math.PI * 2);
    ctx.fill();
  } else {
    // 점 사이를 2차 곡선으로 이어 부드럽게
    ctx.beginPath();
    ctx.moveTo(pts[0][0] * w, pts[0][1] * h);
    for (let i = 1; i < pts.length - 1; i++) {
      const mx = ((pts[i][0] + pts[i + 1][0]) / 2) * w;
      const my = ((pts[i][1] + pts[i + 1][1]) / 2) * h;
      ctx.quadraticCurveTo(pts[i][0] * w, pts[i][1] * h, mx, my);
    }
    const last = pts[pts.length - 1];
    ctx.lineTo(last[0] * w, last[1] * h);
    ctx.stroke();
  }
  ctx.restore();
}

/** 지우개(타원 반경 rx, ry)가 획에 닿는지. 선 굵기도 고려 */
function hits(s: Stroke, x: number, y: number, rx: number, ry: number, w: number) {
  const pad = (s.width * w) / 2 / w; // 선 굵기 절반 (비율)
  const ex = rx + pad;
  const ey = ry + pad;
  const pts = s.points;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[i + 1] ?? a;
    if (segDist((x - a[0]) / ex, (y - a[1]) / ey, (b[0] - a[0]) / ex, (b[1] - a[1]) / ey) <= 1) return true;
  }
  return false;
}

/** 원점 기준 (px,py)에서 선분 (0,0)-(bx,by)까지 거리 */
function segDist(px: number, py: number, bx: number, by: number) {
  const len = bx * bx + by * by;
  const t = len ? Math.max(0, Math.min(1, (px * bx + py * by) / len)) : 0;
  return Math.hypot(px - t * bx, py - t * by);
}
