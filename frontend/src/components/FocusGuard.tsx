// 집중 도우미 화면 조각: 켜기 버튼, 카메라 미리보기, "집중!" 알림
import { Camera, CameraOff, Loader2, X } from 'lucide-react';
import rabbitFace from '../assets/rabbit-face.png';
import type { FocusReason, useFocusGuard } from '../hooks/useFocusGuard';

type Guard = ReturnType<typeof useFocusGuard>;

const REASON: Record<FocusReason, string> = {
  away: '화면을 보고 있지 않아요. 수업 자료를 봐 주세요!',
  noFace: '얼굴이 보이지 않아요. 화면 앞으로 돌아와 주세요!',
  closed: '눈을 감고 있어요. 눈을 뜨고 같이 봐요!',
  still: '눈이 한참 멈춰 있어요. 지금 읽는 곳을 따라가 봐요!',
};

/** 켜기·끄기 버튼 */
export function FocusToggle({ guard, compact = false }: { guard: Guard; compact?: boolean }) {
  const on = guard.status === 'watching' || guard.status === 'starting';
  return (
    <button
      type="button"
      className={`focus-toggle ${on ? 'on' : ''} ${compact ? 'compact' : ''}`}
      onClick={on ? guard.stop : guard.start}
      disabled={guard.status === 'starting'}
      title={on ? '집중 도우미 끄기' : '집중 도우미 켜기 (카메라 영상은 이 기기에서만 분석하고 저장하지 않아요)'}
      aria-pressed={on}
    >
      {guard.status === 'starting' ? <Loader2 size={15} className="spin" /> : on ? <Camera size={15} /> : <CameraOff size={15} />}
      {compact ? null : guard.status === 'starting' ? '켜는 중…' : on ? '집중 도우미 켜짐' : '집중 도우미'}
    </button>
  );
}

/** 카메라가 켜져 있다는 걸 학생이 알 수 있게 보여주는 작은 미리보기 (왼쪽 아래) */
export function FocusPreview({ guard }: { guard: Guard }) {
  const visible = guard.status === 'watching' || guard.status === 'starting';
  return (
    <div className={`focus-preview ${visible ? '' : 'hidden'}`} aria-hidden={!visible}>
      <video ref={guard.videoRef} muted playsInline />
      <div className="focus-preview-bar">
        <span className="dot" /> 집중 도우미{guard.demo ? ' (시연)' : ''}
        <button type="button" aria-label="집중 도우미 끄기" onClick={guard.stop}>
          <X size={13} />
        </button>
      </div>
      <p>영상은 저장하거나 보내지 않아요</p>
    </div>
  );
}

/** "집중!" 알림: 배경 없이 화면 가운데에 [집] [토끼 얼굴] [중]을 한 줄로 크게 */
export function FocusAlert({ guard }: { guard: Guard }) {
  if (!guard.alert) return null;
  return (
    <div className="focus-alert" role="alert" aria-labelledby="focus-alert-title" aria-describedby="focus-alert-desc">
      <h2 id="focus-alert-title" className="focus-line" aria-label="집중">
        <span className="focus-char" aria-hidden>
          집
        </span>
        <img className="focus-face" src={rabbitFace} alt="" draggable={false} />
        <span className="focus-char" aria-hidden>
          중
        </span>
      </h2>
      <p id="focus-alert-desc" className="sr-only">
        {REASON[guard.alert]}
      </p>
      <button type="button" className="focus-back" onClick={guard.dismiss}>
        다시 집중할게요
      </button>
    </div>
  );
}

/** 켜기 실패 안내 */
export function FocusError({ guard }: { guard: Guard }) {
  if (guard.status !== 'error' || !guard.error) return null;
  return <div className="interim">{guard.error}</div>;
}
